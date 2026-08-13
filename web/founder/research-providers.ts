import { sha256Hex } from "./crypto.ts";
import type { D1DatabaseLike, D1StatementLike } from "./database.ts";
import { RESEARCH_AUTHORITY, RESEARCH_BOUNDARY } from "./research-database.ts";

const MAX_PROVIDER_BYTES = 4_194_304;
const PROVIDER_TIMEOUT_MS = 15_000;
const MAX_INSERT_BATCH = 50;

type ProviderEnv = {
  DELTAGRID_SYSTEM_DB?: D1DatabaseLike;
  DELTAGRID_FOUNDER_EMAIL?: string;
  ALPHA_VANTAGE_API_KEY?: string;
  FRED_API_KEY?: string;
};

type DueInstrument = {
  provider_id: "COINBASE_EXCHANGE" | "ALPHA_VANTAGE" | "FRED" | "SEC_COMPANYFACTS" | "US_TREASURY_FISCALDATA";
  instrument_id: string;
  provider_symbol: string;
  symbol: string;
  cik: string | null;
  cadence_seconds: number;
};

type CollectionResult = {
  responseSha256: string;
  responseBytes: number;
  recordCount: number;
};

export async function collectDueResearchProviders(env: ProviderEnv, scheduledTime: number): Promise<void> {
  const db = env.DELTAGRID_SYSTEM_DB;
  if (!db) throw new Error("RESEARCH_DATABASE_BINDING_MISSING");
  const now = new Date(scheduledTime).toISOString();
  const dueProviders = await db.prepare(
    `SELECT s.provider_id, MIN(s.next_due_at) AS earliest_due_at
     FROM research_provider_state s JOIN research_instruments i ON i.instrument_id = s.instrument_id
     WHERE i.enabled = 1 AND s.next_due_at <= ?
     GROUP BY s.provider_id
     ORDER BY earliest_due_at, s.provider_id`,
  ).bind(now).all<{ provider_id: DueInstrument["provider_id"] }>();
  if (!dueProviders.success) throw new Error("RESEARCH_DUE_PROVIDER_QUERY_FAILED");

  const outcomes = await Promise.allSettled(
    (dueProviders.results ?? []).map((provider) => collectNextResearchProvider(env, scheduledTime, provider.provider_id)),
  );
  if (outcomes.some((outcome) => outcome.status === "rejected")) {
    throw new Error("RESEARCH_PROVIDER_BATCH_INCOMPLETE");
  }
}

export async function collectNextResearchProvider(
  env: ProviderEnv,
  scheduledTime: number,
  providerId?: DueInstrument["provider_id"],
): Promise<void> {
  const db = env.DELTAGRID_SYSTEM_DB;
  if (!db) throw new Error("RESEARCH_DATABASE_BINDING_MISSING");
  const now = new Date(scheduledTime).toISOString();
  const due = await db.prepare(
    `SELECT s.provider_id, s.instrument_id, i.provider_symbol, i.symbol, i.cik, i.cadence_seconds
     FROM research_provider_state s JOIN research_instruments i ON i.instrument_id = s.instrument_id
     WHERE i.enabled = 1 AND s.next_due_at <= ? AND (? IS NULL OR s.provider_id = ?)
     ORDER BY s.next_due_at,
       COALESCE((
         SELECT MAX(peer.last_attempt_at) FROM research_provider_state peer
         WHERE peer.provider_id = s.provider_id
       ), '1970-01-01T00:00:00.000Z'),
       s.provider_id, s.instrument_id
     LIMIT 1`,
  ).bind(now, providerId ?? null, providerId ?? null).first<DueInstrument>();
  if (!due) return;

  const bucket = new Date(Math.floor(scheduledTime / 900_000) * 900_000).toISOString();
  const claim = await db.prepare(
    `INSERT OR IGNORE INTO research_collection_claims (
      provider_id, instrument_id, scheduled_bucket, claimed_at
    ) VALUES (?, ?, ?, ?) RETURNING scheduled_bucket`,
  ).bind(due.provider_id, due.instrument_id, bucket, now).run<{ scheduled_bucket: string }>();
  if (!claim.success || !changedExactlyOne(claim)) return;

  let outcome: "OPERATIONAL" | "DEGRADED" | "FAILED" = "OPERATIONAL";
  let detailCode = "COLLECTION_SUCCEEDED";
  let result: CollectionResult | null = null;
  try {
    result = await collectProvider(db, due, env, scheduledTime);
  } catch (error) {
    if (error instanceof ProviderCollectionError) {
      detailCode = error.code;
      if (error.responseSha256 && error.responseBytes !== null) {
        result = { responseSha256: error.responseSha256, responseBytes: error.responseBytes, recordCount: 0 };
      }
    } else {
      detailCode = "PROVIDER_COLLECTION_FAILED";
    }
    outcome = detailCode === "PROVIDER_SECRET_MISSING" || detailCode === "PROVIDER_QUOTA_REACHED" ? "DEGRADED" : "FAILED";
  }

  const completedAt = new Date().toISOString();
  const retrySeconds = providerRetrySeconds(outcome, detailCode, due.cadence_seconds);
  const nextDueAt = new Date(scheduledTime + retrySeconds * 1000).toISOString();
  const receiptId = crypto.randomUUID();
  const statements = [
    db.prepare(
      `UPDATE research_provider_state SET status = ?, last_attempt_at = ?,
        last_success_at = CASE WHEN ? = 'OPERATIONAL' THEN ? ELSE last_success_at END,
        next_due_at = ?, detail_code = ?, quota_state = ?, updated_at = ?
       WHERE provider_id = ? AND instrument_id = ?`,
    ).bind(
      outcome, now, outcome, completedAt, nextDueAt, detailCode,
      detailCode === "PROVIDER_QUOTA_REACHED" ? "PROVIDER_LIMIT_REACHED" : "WITHIN_CONFIGURED_BUDGET",
      completedAt, due.provider_id, due.instrument_id,
    ),
    db.prepare(
      `INSERT INTO research_provider_receipts (
        receipt_id, scheduled_bucket, provider_id, instrument_id, attempted_at, completed_at,
        status, response_sha256, response_bytes, record_count, detail_code, boundary, authority_effect
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      receiptId, bucket, due.provider_id, due.instrument_id, now, completedAt, outcome,
      result?.responseSha256 ?? null, result?.responseBytes ?? 0, result?.recordCount ?? 0,
      detailCode, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY,
    ),
    db.prepare(
      `UPDATE research_collection_claims SET completed_at = ?, outcome = ?
       WHERE provider_id = ? AND instrument_id = ? AND scheduled_bucket = ?`,
    ).bind(completedAt, outcome, due.provider_id, due.instrument_id, bucket),
  ];
  if (detailCode === "PROVIDER_QUOTA_REACHED") {
    statements.push(db.prepare(
      `UPDATE research_provider_state SET
        status = CASE WHEN last_success_at IS NULL THEN 'DEGRADED' ELSE status END,
        next_due_at = CASE WHEN next_due_at < ? THEN ? ELSE next_due_at END,
        detail_code = 'PROVIDER_QUOTA_REACHED', quota_state = 'PROVIDER_LIMIT_REACHED', updated_at = ?
       WHERE provider_id = ?`,
    ).bind(nextDueAt, nextDueAt, completedAt, due.provider_id));
  }
  const saved = await db.batch(statements);
  if (saved.some((entry) => !entry.success)) throw new Error("RESEARCH_COLLECTION_RECEIPT_FAILED");
  console.log(JSON.stringify({
    event: "research_provider_collection",
    provider_id: due.provider_id,
    instrument_id: due.instrument_id,
    status: outcome,
    detail_code: detailCode,
    record_count: result?.recordCount ?? 0,
    boundary: RESEARCH_BOUNDARY,
    authority_effect: RESEARCH_AUTHORITY,
  }));
}

async function collectProvider(
  db: D1DatabaseLike,
  instrument: DueInstrument,
  env: ProviderEnv,
  scheduledTime: number,
): Promise<CollectionResult> {
  if (instrument.provider_id === "COINBASE_EXCHANGE") return collectCoinbase(db, instrument, env, scheduledTime);
  if (instrument.provider_id === "ALPHA_VANTAGE") return collectAlphaVantage(db, instrument, env, scheduledTime);
  if (instrument.provider_id === "FRED") return collectFred(db, instrument, env, scheduledTime);
  if (instrument.provider_id === "SEC_COMPANYFACTS") return collectSec(db, instrument, env, scheduledTime);
  return collectTreasury(db, instrument, env, scheduledTime);
}

async function collectCoinbase(
  db: D1DatabaseLike,
  instrument: DueInstrument,
  env: ProviderEnv,
  scheduledTime: number,
): Promise<CollectionResult> {
  const window = coinbaseCandleWindow(scheduledTime);
  const url = new URL(`https://api.exchange.coinbase.com/products/${encodeURIComponent(instrument.provider_symbol)}/candles`);
  url.searchParams.set("granularity", "3600");
  url.searchParams.set("start", window.start);
  url.searchParams.set("end", window.end);
  const payload = await fetchProviderPayload(url, identifiedHeaders(env));
  let rows: Array<{ time: number; low: number; high: number; open: number; close: number; volume: number }>;
  try {
    const decoded = parseProviderJson(payload.text);
    if (!Array.isArray(decoded) || decoded.length > 300) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
    rows = decoded.map((entry) => {
      if (!Array.isArray(entry) || entry.length < 6 || entry.slice(0, 6).some((value) => !finiteNumber(value))) {
        throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
      }
      const [time, low, high, open, close, volume] = entry.map(Number);
      return { time, low, high, open, close, volume };
    }).filter((row) => row.time * 1000 < window.settledBeforeMs);
  } catch (error) {
    if (error instanceof ProviderCollectionError) {
      throw new ProviderCollectionError(error.code, payload.sha256, payload.bytes);
    }
    throw error;
  }
  const statements = rows.map((row) => db.prepare(
    `INSERT INTO research_price_observations (
      instrument_id, observed_at, available_at, interval, open, high, low, close, volume,
      adjusted, source_sha256, boundary, authority_effect
    ) VALUES (?, ?, ?, 'HOUR', ?, ?, ?, ?, ?, 0, ?, ?, ?)
    ON CONFLICT(instrument_id, observed_at, interval) DO UPDATE SET
      available_at=excluded.available_at, open=excluded.open, high=excluded.high, low=excluded.low,
      close=excluded.close, volume=excluded.volume, source_sha256=excluded.source_sha256`,
  ).bind(
    instrument.instrument_id, new Date(row.time * 1000).toISOString(), new Date(scheduledTime).toISOString(),
    row.open, row.high, row.low, row.close, row.volume, payload.sha256, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY,
  ));
  await runBatches(db, statements);
  return { responseSha256: payload.sha256, responseBytes: payload.bytes, recordCount: rows.length };
}

async function collectAlphaVantage(
  db: D1DatabaseLike,
  instrument: DueInstrument,
  env: ProviderEnv,
  scheduledTime: number,
): Promise<CollectionResult> {
  const key = env.ALPHA_VANTAGE_API_KEY?.trim();
  if (!key) throw new ProviderCollectionError("PROVIDER_SECRET_MISSING");
  const url = new URL("https://www.alphavantage.co/query");
  url.searchParams.set("function", "TIME_SERIES_DAILY");
  url.searchParams.set("symbol", instrument.provider_symbol);
  url.searchParams.set("outputsize", "compact");
  url.searchParams.set("apikey", key);
  const payload = await fetchProviderPayload(url, identifiedHeaders(env));
  let entries: ReturnType<typeof parseAlphaDaily>;
  try {
    entries = parseAlphaDaily(payload.text);
  } catch (error) {
    if (error instanceof ProviderCollectionError) {
      throw new ProviderCollectionError(error.code, payload.sha256, payload.bytes);
    }
    throw error;
  }
  const statements = entries.map(({ date, open, high, low, close, volume }) => {
    return db.prepare(
      `INSERT INTO research_price_observations (
        instrument_id, observed_at, available_at, interval, open, high, low, close, volume,
        adjusted, source_sha256, boundary, authority_effect
      ) VALUES (?, ?, ?, 'DAY', ?, ?, ?, ?, ?, 0, ?, ?, ?)
      ON CONFLICT(instrument_id, observed_at, interval) DO UPDATE SET
        available_at=excluded.available_at, open=excluded.open, high=excluded.high, low=excluded.low,
        close=excluded.close, volume=excluded.volume, source_sha256=excluded.source_sha256`,
    ).bind(
      instrument.instrument_id, `${date}T00:00:00.000Z`, new Date(scheduledTime).toISOString(),
      open, high, low, close, volume, payload.sha256, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY,
    );
  });
  await runBatches(db, statements);
  return { responseSha256: payload.sha256, responseBytes: payload.bytes, recordCount: entries.length };
}

async function collectFred(
  db: D1DatabaseLike,
  instrument: DueInstrument,
  env: ProviderEnv,
  scheduledTime: number,
): Promise<CollectionResult> {
  const key = env.FRED_API_KEY?.trim();
  if (!key) throw new ProviderCollectionError("PROVIDER_SECRET_MISSING");
  const url = new URL("https://api.stlouisfed.org/fred/series/observations");
  url.searchParams.set("series_id", instrument.provider_symbol);
  url.searchParams.set("api_key", key);
  url.searchParams.set("file_type", "json");
  url.searchParams.set("sort_order", "desc");
  url.searchParams.set("limit", "120");
  const payload = await fetchProviderPayload(url, identifiedHeaders(env));
  const decoded = objectValue(parseProviderJson(payload.text));
  if (!Array.isArray(decoded.observations) || decoded.observations.length > 120) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
  const unit = fredUnit(instrument.provider_symbol);
  const frequency = fredFrequency(instrument.provider_symbol);
  const observations = decoded.observations.flatMap((raw) => {
    const row = objectValue(raw);
    if (typeof row.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/u.test(row.date) || row.value === ".") return [];
    return [{ date: row.date, value: exactFinite(row.value) }];
  });
  const statements = observations.map((row) => db.prepare(
    `INSERT INTO research_macro_observations (
      instrument_id, observed_at, available_at, value, unit, frequency,
      source_sha256, boundary, authority_effect
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(instrument_id, observed_at) DO UPDATE SET
      available_at=excluded.available_at, value=excluded.value, unit=excluded.unit,
      frequency=excluded.frequency, source_sha256=excluded.source_sha256`,
  ).bind(
    instrument.instrument_id, `${row.date}T00:00:00.000Z`, new Date(scheduledTime).toISOString(),
    row.value, unit, frequency, payload.sha256, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY,
  ));
  await runBatches(db, statements);
  return { responseSha256: payload.sha256, responseBytes: payload.bytes, recordCount: observations.length };
}

async function collectSec(
  db: D1DatabaseLike,
  instrument: DueInstrument,
  env: ProviderEnv,
  scheduledTime: number,
): Promise<CollectionResult> {
  const cik = instrument.cik;
  if (!cik || !/^\d{10}$/u.test(cik)) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
  const payload = await fetchProviderPayload(new URL(`https://data.sec.gov/api/xbrl/companyfacts/CIK${cik}.json`), identifiedHeaders(env));
  const decoded = objectValue(parseProviderJson(payload.text));
  const facts = objectValue(objectValue(decoded.facts)["us-gaap"]);
  const metricKeys = ["Assets", "Liabilities", "Revenues", "NetIncomeLoss", "StockholdersEquity"];
  const rows: Array<{ metric: string; end: string; filed: string; form: string; value: number; accn: string }> = [];
  for (const metric of metricKeys) {
    const fact = facts[metric];
    if (!fact || typeof fact !== "object") continue;
    const units = objectValue(objectValue(fact).units);
    const values = Array.isArray(units.USD) ? units.USD : [];
    for (const raw of values.slice(-12)) {
      const row = objectValue(raw);
      if ((row.form !== "10-K" && row.form !== "10-Q") || typeof row.end !== "string" || typeof row.filed !== "string" || typeof row.accn !== "string") continue;
      rows.push({ metric, end: row.end, filed: row.filed, form: row.form, value: exactFinite(row.val), accn: row.accn });
    }
  }
  if (rows.length === 0 || rows.length > 60) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
  const statements = rows.map((row) => db.prepare(
    `INSERT INTO research_fundamental_facts (
      instrument_id, metric_key, period_end, filed_at, form, unit, value,
      accession_number, available_at, source_sha256, boundary, authority_effect
    ) VALUES (?, ?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?, ?)
    ON CONFLICT(instrument_id, metric_key, period_end, accession_number) DO UPDATE SET
      filed_at=excluded.filed_at, form=excluded.form, value=excluded.value,
      available_at=excluded.available_at, source_sha256=excluded.source_sha256`,
  ).bind(
    instrument.instrument_id, row.metric, row.end, row.filed, row.form, row.value, row.accn,
    new Date(scheduledTime).toISOString(), payload.sha256, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY,
  ));
  await runBatches(db, statements);
  return { responseSha256: payload.sha256, responseBytes: payload.bytes, recordCount: rows.length };
}

async function collectTreasury(
  db: D1DatabaseLike,
  instrument: DueInstrument,
  env: ProviderEnv,
  scheduledTime: number,
): Promise<CollectionResult> {
  const url = new URL("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny");
  url.searchParams.set("sort", "-record_date");
  url.searchParams.set("page[size]", "1");
  const payload = await fetchProviderPayload(url, identifiedHeaders(env));
  const decoded = objectValue(parseProviderJson(payload.text));
  if (!Array.isArray(decoded.data) || decoded.data.length !== 1) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
  const row = objectValue(decoded.data[0]);
  if (typeof row.record_date !== "string" || !/^\d{4}-\d{2}-\d{2}$/u.test(row.record_date)) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
  const value = exactFinite(row.tot_pub_debt_out_amt);
  const statement = db.prepare(
    `INSERT INTO research_macro_observations (
      instrument_id, observed_at, available_at, value, unit, frequency,
      source_sha256, boundary, authority_effect
    ) VALUES (?, ?, ?, ?, 'USD', 'DAILY', ?, ?, ?)
    ON CONFLICT(instrument_id, observed_at) DO UPDATE SET
      available_at=excluded.available_at, value=excluded.value, source_sha256=excluded.source_sha256`,
  ).bind(
    instrument.instrument_id, `${row.record_date}T00:00:00.000Z`, new Date(scheduledTime).toISOString(),
    value, payload.sha256, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY,
  );
  await runBatches(db, [statement]);
  return { responseSha256: payload.sha256, responseBytes: payload.bytes, recordCount: 1 };
}

export async function fetchProviderPayload(
  url: URL,
  headers: Headers,
  maximumBytes = MAX_PROVIDER_BYTES,
  timeoutMs = PROVIDER_TIMEOUT_MS,
  fetcher: typeof fetch = fetch,
): Promise<{ text: string; bytes: number; sha256: string }> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort("PROVIDER_TIMEOUT"), timeoutMs);
  let response: Response;
  try {
    response = await fetcher(url, { headers, signal: controller.signal, redirect: "manual" });
  } catch {
    throw new ProviderCollectionError("PROVIDER_NETWORK_FAILURE");
  } finally {
    clearTimeout(timeout);
  }
  if (response.status >= 300 && response.status < 400) {
    throw new ProviderCollectionError("PROVIDER_REDIRECT_REJECTED");
  }
  if (!response.ok) throw new ProviderCollectionError(`PROVIDER_HTTP_${response.status}`);
  const text = await readBoundedText(response, maximumBytes);
  return { text, bytes: new TextEncoder().encode(text).byteLength, sha256: await sha256Hex(text) };
}

export async function readBoundedText(response: Response, maximumBytes: number): Promise<string> {
  const declared = Number(response.headers.get("content-length") ?? 0);
  if (declared > maximumBytes) throw new ProviderCollectionError("PROVIDER_RESPONSE_TOO_LARGE");
  if (!response.body) throw new ProviderCollectionError("PROVIDER_RESPONSE_EMPTY");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0;
  let output = "";
  while (true) {
    const result = await reader.read();
    if (result.done) break;
    bytes += result.value.byteLength;
    if (bytes > maximumBytes) {
      await reader.cancel("PROVIDER_RESPONSE_TOO_LARGE");
      throw new ProviderCollectionError("PROVIDER_RESPONSE_TOO_LARGE");
    }
    output += decoder.decode(result.value, { stream: true });
  }
  output += decoder.decode();
  return output;
}

export function providerRetrySeconds(
  outcome: "OPERATIONAL" | "DEGRADED" | "FAILED",
  detailCode: string,
  cadenceSeconds: number,
): number {
  if (outcome === "OPERATIONAL") return cadenceSeconds;
  if (detailCode === "PROVIDER_QUOTA_REACHED") return 86_400;
  if (outcome === "DEGRADED") return 21_600;
  return 3_600;
}

export function coinbaseCandleWindow(scheduledTime: number): {
  start: string;
  end: string;
  settledBeforeMs: number;
} {
  const settledBeforeMs = Math.floor(scheduledTime / 3_600_000) * 3_600_000;
  return {
    start: new Date(settledBeforeMs - 240 * 3_600_000).toISOString(),
    end: new Date(settledBeforeMs).toISOString(),
    settledBeforeMs,
  };
}

async function runBatches(db: D1DatabaseLike, statements: D1StatementLike[]): Promise<void> {
  for (let start = 0; start < statements.length; start += MAX_INSERT_BATCH) {
    const results = await db.batch(statements.slice(start, start + MAX_INSERT_BATCH));
    if (results.some((result) => !result.success)) throw new ProviderCollectionError("PROVIDER_STORAGE_FAILED");
  }
}

function identifiedHeaders(env: ProviderEnv): Headers {
  const email = env.DELTAGRID_FOUNDER_EMAIL?.trim();
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(email)) throw new ProviderCollectionError("PROVIDER_IDENTITY_CONFIGURATION_INVALID");
  return new Headers({
    accept: "application/json",
    "user-agent": `DeltaGridResearch/1.0 (${email})`,
  });
}

export function parseProviderJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    throw new ProviderCollectionError("PROVIDER_JSON_INVALID");
  }
}

export function parseAlphaDaily(text: string): Array<{
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}> {
  const decoded = objectValue(parseProviderJson(text));
  if (typeof decoded.Note === "string" || typeof decoded.Information === "string") throw new ProviderCollectionError("PROVIDER_QUOTA_REACHED");
  const entries = Object.entries(objectValue(decoded["Time Series (Daily)"]));
  if (entries.length === 0 || entries.length > 100) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
  return entries.map(([date, raw]) => {
    if (!/^\d{4}-\d{2}-\d{2}$/u.test(date)) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
    const row = objectValue(raw);
    return {
      date,
      open: exactFinite(row["1. open"]),
      high: exactFinite(row["2. high"]),
      low: exactFinite(row["3. low"]),
      close: exactFinite(row["4. close"]),
      volume: exactFinite(row["5. volume"]),
    };
  });
}

function objectValue(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
  return value as Record<string, unknown>;
}

function exactFinite(value: unknown): number {
  const parsed = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  if (!Number.isFinite(parsed)) throw new ProviderCollectionError("PROVIDER_SCHEMA_INVALID");
  return parsed;
}

function finiteNumber(value: unknown): boolean {
  return (typeof value === "number" || typeof value === "string") && Number.isFinite(Number(value));
}

function fredUnit(series: string): string {
  if (["UNRATE", "DFF", "DGS10", "DGS2", "T10Y2Y"].includes(series)) return "PERCENT";
  if (series === "GDP") return "BILLIONS_USD";
  return "INDEX";
}

function fredFrequency(series: string): string {
  if (["DFF", "DGS10", "DGS2", "T10Y2Y", "DTWEXBGS"].includes(series)) return "DAILY";
  if (series === "GDP") return "QUARTERLY";
  return "MONTHLY";
}

function changedExactlyOne(result: { results?: unknown[]; meta?: { changes?: number } }): boolean {
  return result.results?.length === 1 || result.meta?.changes === 1;
}

class ProviderCollectionError extends Error {
  readonly code: string;
  readonly responseSha256: string | null;
  readonly responseBytes: number | null;
  constructor(code: string, responseSha256: string | null = null, responseBytes: number | null = null) {
    super(code);
    this.code = code;
    this.responseSha256 = responseSha256;
    this.responseBytes = responseBytes;
  }
}
