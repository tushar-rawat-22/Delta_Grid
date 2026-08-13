import type { D1DatabaseLike, D1ResultLike } from "./database.ts";
import { calculateMetrics, type ResearchBar } from "./research-metrics.ts";

export const RESEARCH_BOUNDARY = "NON_RAB1_RESEARCH_ONLY" as const;
export const RESEARCH_AUTHORITY = "NONE" as const;

export type ResearchInstrument = {
  instrument_id: string;
  provider_id: string;
  symbol: string;
  display_name: string;
  asset_class: string;
  provider_symbol: string;
  rights_classification: string;
  status: string;
  detail_code: string;
  last_success_at: string | null;
  latest_close: number | null;
  latest_observed_at: string | null;
  latest_interval: string | null;
};

export type ResearchRecord = {
  record_id: string;
  owner_id: string;
  record_type: "NOTE" | "THESIS" | "EVIDENCE" | "JOURNAL" | "CATALYST" | "RISK" | "TASK";
  instrument_id: string | null;
  title: string;
  body: string;
  status: "DRAFT" | "ACTIVE" | "WATCHING" | "DONE" | "ARCHIVED";
  confidence: number | null;
  tags_json: string;
  source_url: string | null;
  source_published_at: string | null;
  source_accessed_at: string | null;
  due_at: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
};

export type ResearchRecordInput = Omit<ResearchRecord, "record_id" | "owner_id" | "revision" | "created_at" | "updated_at">;

export type ResearchWatchlist = {
  watchlist_id: string;
  name: string;
  revision: number;
  created_at: string;
  updated_at: string;
  items: string[];
};

export async function ensureDefaultWatchlist(db: D1DatabaseLike, ownerId: string, now: string): Promise<void> {
  const id = `default-${ownerId}`;
  const insert = await db.prepare(
    `INSERT OR IGNORE INTO research_watchlists (
      watchlist_id, owner_id, name, revision, created_at, updated_at, boundary, authority_effect
    ) VALUES (?, ?, 'Core watchlist', 1, ?, ?, ?, ?)`,
  ).bind(id, ownerId, now, now, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY).run();
  if (!insert.success) throw new Error("RESEARCH_WATCHLIST_INITIALIZATION_FAILED");
  const instruments = ["CRYPTO_BTC_USD", "CRYPTO_ETH_USD", "CRYPTO_SOL_USD", "ETF_SPY", "ETF_QQQ", "EQUITY_AAPL", "EQUITY_MSFT", "EQUITY_NVDA"];
  const statements = instruments.map((instrumentId, position) => db.prepare(
    "INSERT OR IGNORE INTO research_watchlist_items (watchlist_id, instrument_id, position, added_at) VALUES (?, ?, ?, ?)",
  ).bind(id, instrumentId, position, now));
  const results = await db.batch(statements);
  if (results.some((result) => !result.success)) throw new Error("RESEARCH_WATCHLIST_ITEMS_INITIALIZATION_FAILED");
}

export async function listResearchInstruments(db: D1DatabaseLike): Promise<ResearchInstrument[]> {
  const result = await db.prepare(
    `SELECT i.instrument_id, i.provider_id, i.symbol, i.display_name, i.asset_class,
      i.provider_symbol, i.rights_classification,
      COALESCE(s.status, 'PENDING') AS status,
      COALESCE(s.detail_code, 'AWAITING_FIRST_COLLECTION') AS detail_code,
      s.last_success_at,
      (SELECT p.close FROM research_price_observations p
        WHERE p.instrument_id = i.instrument_id ORDER BY p.observed_at DESC LIMIT 1) AS latest_close,
      (SELECT p.observed_at FROM research_price_observations p
        WHERE p.instrument_id = i.instrument_id ORDER BY p.observed_at DESC LIMIT 1) AS latest_observed_at,
      (SELECT p.interval FROM research_price_observations p
        WHERE p.instrument_id = i.instrument_id ORDER BY p.observed_at DESC LIMIT 1) AS latest_interval
    FROM research_instruments i
    LEFT JOIN research_provider_state s ON s.instrument_id = i.instrument_id AND s.provider_id = i.provider_id
    WHERE i.enabled = 1 AND i.asset_class IN ('CRYPTO', 'US_EQUITY', 'US_ETF')
    ORDER BY CASE i.asset_class WHEN 'CRYPTO' THEN 1 WHEN 'US_ETF' THEN 2 ELSE 3 END, i.symbol`,
  ).all<ResearchInstrument>();
  if (!result.success) throw new Error("RESEARCH_INSTRUMENT_LIST_FAILED");
  return result.results ?? [];
}

export async function listWatchlists(db: D1DatabaseLike, ownerId: string): Promise<ResearchWatchlist[]> {
  const lists = await db.prepare(
    "SELECT watchlist_id, name, revision, created_at, updated_at FROM research_watchlists WHERE owner_id = ? ORDER BY updated_at DESC",
  ).bind(ownerId).all<Omit<ResearchWatchlist, "items">>();
  if (!lists.success) throw new Error("RESEARCH_WATCHLIST_LIST_FAILED");
  const output: ResearchWatchlist[] = [];
  for (const list of lists.results ?? []) {
    const items = await db.prepare(
      "SELECT instrument_id FROM research_watchlist_items WHERE watchlist_id = ? ORDER BY position, instrument_id",
    ).bind(list.watchlist_id).all<{ instrument_id: string }>();
    if (!items.success) throw new Error("RESEARCH_WATCHLIST_ITEM_LIST_FAILED");
    output.push({ ...list, items: (items.results ?? []).map((item) => item.instrument_id) });
  }
  return output;
}

export async function createWatchlist(
  db: D1DatabaseLike,
  ownerId: string,
  name: string,
  instrumentIds: string[],
  now: string,
): Promise<ResearchWatchlist> {
  const watchlistId = crypto.randomUUID();
  const results = await db.batch([
    db.prepare(
      `INSERT INTO research_watchlists (
        watchlist_id, owner_id, name, revision, created_at, updated_at, boundary, authority_effect
      ) VALUES (?, ?, ?, 1, ?, ?, ?, ?) RETURNING watchlist_id`,
    ).bind(watchlistId, ownerId, name, now, now, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY),
    ...instrumentIds.map((instrumentId, position) => db.prepare(
      "INSERT INTO research_watchlist_items (watchlist_id, instrument_id, position, added_at) VALUES (?, ?, ?, ?)",
    ).bind(watchlistId, instrumentId, position, now)),
  ]);
  if (results.some((result) => !result.success)) throw new Error("RESEARCH_WATCHLIST_CREATE_FAILED");
  return { watchlist_id: watchlistId, name, revision: 1, created_at: now, updated_at: now, items: instrumentIds };
}

export async function replaceWatchlist(
  db: D1DatabaseLike,
  ownerId: string,
  watchlistId: string,
  name: string,
  expectedRevision: number,
  instrumentIds: string[],
  now: string,
): Promise<ResearchWatchlist | null> {
  const statements = [
    db.prepare(
      `UPDATE research_watchlists SET name = ?, revision = revision + 1, updated_at = ?
       WHERE watchlist_id = ? AND owner_id = ? AND revision = ? RETURNING watchlist_id`,
    ).bind(name, now, watchlistId, ownerId, expectedRevision),
    db.prepare(
      `DELETE FROM research_watchlist_items WHERE watchlist_id = ? AND EXISTS (
        SELECT 1 FROM research_watchlists WHERE watchlist_id = ? AND owner_id = ? AND revision = ?
      )`,
    ).bind(watchlistId, watchlistId, ownerId, expectedRevision + 1),
    ...instrumentIds.map((instrumentId, position) => db.prepare(
      `INSERT INTO research_watchlist_items (watchlist_id, instrument_id, position, added_at)
       SELECT ?, ?, ?, ? WHERE EXISTS (
         SELECT 1 FROM research_watchlists WHERE watchlist_id = ? AND owner_id = ? AND revision = ?
       )`,
    ).bind(watchlistId, instrumentId, position, now, watchlistId, ownerId, expectedRevision + 1)),
  ];
  const results = await db.batch(statements);
  if (!results[0]?.success || !changedExactlyOne(results[0])) return null;
  if (results.some((result) => !result.success)) throw new Error("RESEARCH_WATCHLIST_UPDATE_FAILED");
  return (await listWatchlists(db, ownerId)).find((list) => list.watchlist_id === watchlistId) ?? null;
}

export async function getPriceBars(db: D1DatabaseLike, instrumentId: string, limit = 300): Promise<ResearchBar[]> {
  const bounded = Math.max(2, Math.min(limit, 1000));
  const result = await db.prepare(
    `SELECT observed_at, close FROM research_price_observations
     WHERE instrument_id = ? ORDER BY observed_at DESC LIMIT ?`,
  ).bind(instrumentId, bounded).all<ResearchBar>();
  if (!result.success) throw new Error("RESEARCH_PRICE_SERIES_FAILED");
  return (result.results ?? []).toReversed();
}

export async function getInstrumentDossier(db: D1DatabaseLike, instrumentId: string): Promise<Record<string, unknown> | null> {
  const instrument = await db.prepare(
    `SELECT instrument_id, provider_id, symbol, display_name, asset_class, provider_symbol,
      rights_classification FROM research_instruments
     WHERE instrument_id = ? AND enabled = 1 AND asset_class IN ('CRYPTO', 'US_EQUITY', 'US_ETF')`,
  ).bind(instrumentId).first<Record<string, unknown>>();
  if (!instrument) return null;
  const bars = await getPriceBars(db, instrumentId);
  const annualization = instrument.asset_class === "CRYPTO" ? 365 : 252;
  const fundamentals = await db.prepare(
    `SELECT f.metric_key, f.period_end, f.filed_at, f.form, f.unit, f.value, f.available_at
     FROM research_fundamental_facts f JOIN research_instruments fi ON fi.instrument_id = f.instrument_id
     WHERE fi.symbol = ? ORDER BY f.period_end DESC, f.metric_key LIMIT 24`,
  ).bind(String(instrument.symbol)).all<Record<string, unknown>>();
  if (!fundamentals.success) throw new Error("RESEARCH_FUNDAMENTALS_FAILED");
  return { instrument, bars, metrics: calculateMetrics(bars, annualization), fundamentals: fundamentals.results ?? [] };
}

export async function listMacro(db: D1DatabaseLike): Promise<Record<string, unknown>[]> {
  const result = await db.prepare(
    `SELECT i.instrument_id, i.symbol, i.display_name, i.provider_id, i.rights_classification,
      s.status, s.detail_code, s.last_success_at,
      (SELECT m.value FROM research_macro_observations m WHERE m.instrument_id = i.instrument_id ORDER BY m.observed_at DESC LIMIT 1) AS latest_value,
      (SELECT m.unit FROM research_macro_observations m WHERE m.instrument_id = i.instrument_id ORDER BY m.observed_at DESC LIMIT 1) AS unit,
      (SELECT m.frequency FROM research_macro_observations m WHERE m.instrument_id = i.instrument_id ORDER BY m.observed_at DESC LIMIT 1) AS frequency,
      (SELECT m.observed_at FROM research_macro_observations m WHERE m.instrument_id = i.instrument_id ORDER BY m.observed_at DESC LIMIT 1) AS observed_at,
      (SELECT m2.value FROM research_macro_observations m2 WHERE m2.instrument_id = i.instrument_id ORDER BY m2.observed_at DESC LIMIT 1 OFFSET 1) AS previous_value
    FROM research_instruments i LEFT JOIN research_provider_state s
      ON s.provider_id = i.provider_id AND s.instrument_id = i.instrument_id
    WHERE i.enabled = 1 AND i.asset_class = 'MACRO' ORDER BY i.display_name`,
  ).all<Record<string, unknown>>();
  if (!result.success) throw new Error("RESEARCH_MACRO_LIST_FAILED");
  return result.results ?? [];
}

export async function listProviderHealth(db: D1DatabaseLike): Promise<Record<string, unknown>[]> {
  const result = await db.prepare(
    `SELECT s.provider_id, s.instrument_id, i.symbol, i.display_name, s.status,
      s.last_attempt_at, s.last_success_at, s.next_due_at, s.detail_code,
      s.quota_state, s.rights_classification
    FROM research_provider_state s JOIN research_instruments i ON i.instrument_id = s.instrument_id
    ORDER BY s.provider_id, i.symbol`,
  ).all<Record<string, unknown>>();
  if (!result.success) throw new Error("RESEARCH_PROVIDER_HEALTH_FAILED");
  return result.results ?? [];
}

export async function listRecords(
  db: D1DatabaseLike,
  ownerId: string,
  type?: string,
  includeArchived = false,
): Promise<ResearchRecord[]> {
  const clauses = ["owner_id = ?"];
  const bindings: unknown[] = [ownerId];
  if (type) {
    clauses.push("record_type = ?");
    bindings.push(type);
  }
  if (!includeArchived) clauses.push("status != 'ARCHIVED'");
  const result = await db.prepare(
    `SELECT record_id, owner_id, record_type, instrument_id, title, body, status,
      confidence, tags_json, source_url, source_published_at, source_accessed_at,
      due_at, revision, created_at, updated_at
     FROM research_records WHERE ${clauses.join(" AND ")} ORDER BY updated_at DESC LIMIT 500`,
  ).bind(...bindings).all<ResearchRecord>();
  if (!result.success) throw new Error("RESEARCH_RECORD_LIST_FAILED");
  return result.results ?? [];
}

export async function createRecord(
  db: D1DatabaseLike,
  ownerId: string,
  input: ResearchRecordInput,
  now: string,
): Promise<ResearchRecord> {
  const record: ResearchRecord = {
    ...input,
    record_id: crypto.randomUUID(),
    owner_id: ownerId,
    revision: 1,
    created_at: now,
    updated_at: now,
  };
  const result = await db.prepare(
      `INSERT INTO research_records (
        record_id, owner_id, record_type, instrument_id, title, body, status, confidence,
        tags_json, source_url, source_published_at, source_accessed_at, due_at, revision,
        created_at, updated_at, boundary, authority_effect
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?) RETURNING record_id`,
    ).bind(
      record.record_id, ownerId, record.record_type, record.instrument_id, record.title, record.body,
      record.status, record.confidence, record.tags_json, record.source_url, record.source_published_at,
      record.source_accessed_at, record.due_at, now, now, RESEARCH_BOUNDARY, RESEARCH_AUTHORITY,
    ).run<{ record_id: string }>();
  if (!result.success || !changedExactlyOne(result)) throw new Error("RESEARCH_RECORD_CREATE_FAILED");
  return record;
}

export async function updateRecord(
  db: D1DatabaseLike,
  ownerId: string,
  recordId: string,
  expectedRevision: number,
  input: ResearchRecordInput,
  now: string,
): Promise<ResearchRecord | null> {
  const existing = await db.prepare(
    "SELECT created_at FROM research_records WHERE record_id = ? AND owner_id = ? AND revision = ?",
  ).bind(recordId, ownerId, expectedRevision).first<{ created_at: string }>();
  if (!existing) return null;
  const record: ResearchRecord = {
    ...input,
    record_id: recordId,
    owner_id: ownerId,
    revision: expectedRevision + 1,
    created_at: existing.created_at,
    updated_at: now,
  };
  const result = await db.prepare(
      `UPDATE research_records SET record_type = ?, instrument_id = ?, title = ?, body = ?,
        status = ?, confidence = ?, tags_json = ?, source_url = ?, source_published_at = ?,
        source_accessed_at = ?, due_at = ?, revision = revision + 1, updated_at = ?
       WHERE record_id = ? AND owner_id = ? AND revision = ? RETURNING record_id`,
    ).bind(
      record.record_type, record.instrument_id, record.title, record.body, record.status,
      record.confidence, record.tags_json, record.source_url, record.source_published_at,
      record.source_accessed_at, record.due_at, now, recordId, ownerId, expectedRevision,
    ).run<{ record_id: string }>();
  if (!result.success || !changedExactlyOne(result)) return null;
  return record;
}

export async function listRecordRevisions(db: D1DatabaseLike, ownerId: string, recordId: string): Promise<Record<string, unknown>[]> {
  const result = await db.prepare(
    `SELECT revision_id, revision, snapshot_json, recorded_at FROM research_record_revisions
     WHERE record_id = ? AND owner_id = ? ORDER BY revision DESC`,
  ).bind(recordId, ownerId).all<Record<string, unknown>>();
  if (!result.success) throw new Error("RESEARCH_RECORD_REVISION_LIST_FAILED");
  return result.results ?? [];
}

export async function recentDashboard(db: D1DatabaseLike, ownerId: string): Promise<Record<string, unknown>> {
  const [instruments, watchlists, records, macro, health] = await Promise.all([
    listResearchInstruments(db),
    listWatchlists(db, ownerId),
    listRecords(db, ownerId),
    listMacro(db),
    listProviderHealth(db),
  ]);
  return {
    instruments,
    watchlists,
    records: records.slice(0, 50),
    macro,
    provider_health: health,
    boundary: RESEARCH_BOUNDARY,
    authority_effect: RESEARCH_AUTHORITY,
  };
}

function changedExactlyOne(result: D1ResultLike): boolean {
  return result.results?.length === 1 || result.meta?.changes === 1;
}
