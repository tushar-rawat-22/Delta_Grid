import assert from "node:assert/strict";
import fs from "node:fs";
import { DatabaseSync, type SQLInputValue, type StatementSync } from "node:sqlite";
import test from "node:test";
import { handleResearchApi } from "../founder/research-api.ts";
import type { D1DatabaseLike, D1ResultLike, D1StatementLike } from "../founder/database.ts";

class SqliteStatement implements D1StatementLike {
  private values: SQLInputValue[] = [];
  private readonly statement: StatementSync;
  constructor(statement: StatementSync) { this.statement = statement; }
  bind(...values: unknown[]): D1StatementLike { this.values = values.map(sqlValue); return this; }
  async first<T>(): Promise<T | null> { return (this.statement.get(...this.values) as T | undefined) ?? null; }
  async all<T>(): Promise<D1ResultLike<T>> { return { success: true, results: this.statement.all(...this.values) as T[] }; }
  async run<T>(): Promise<D1ResultLike<T>> {
    if (/\bRETURNING\b/iu.test(this.statement.sourceSQL)) return { success: true, results: this.statement.all(...this.values) as T[] };
    const result = this.statement.run(...this.values);
    return { success: true, results: [], meta: { changes: Number(result.changes) } };
  }
}

function sqlValue(value: unknown): SQLInputValue {
  if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "bigint" || value instanceof Uint8Array) return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  throw new Error("TEST_SQL_VALUE_UNSUPPORTED");
}

class SqliteD1 implements D1DatabaseLike {
  readonly database = new DatabaseSync(":memory:");
  constructor() {
    for (const migration of fs.readdirSync("migrations").filter((name) => name.endsWith(".sql")).sort()) {
      this.database.exec(fs.readFileSync(`migrations/${migration}`, "utf8"));
    }
  }
  prepare(query: string): D1StatementLike { return new SqliteStatement(this.database.prepare(query)); }
  async batch<T>(statements: D1StatementLike[]): Promise<D1ResultLike<T>[]> {
    const output: D1ResultLike<T>[] = [];
    this.database.exec("BEGIN IMMEDIATE");
    try {
      for (const statement of statements) output.push(await statement.run<T>());
      this.database.exec("COMMIT");
      return output;
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }
}

const identity = { subject: "founder-subject", email: "founder@example.test", expiresAt: 1_900_000_000 };

test("research API supports founder-scoped revisioned CRUD and fails closed on stale writes", async () => {
  const db = new SqliteD1();
  const env = { DELTAGRID_SYSTEM_DB: db, DELTAGRID_RESEARCH_CSRF_KEY: "c".repeat(64) };
  const bootstrap = await handleResearchApi(new Request("https://founder.example.test/api/research/v1/bootstrap"), env, identity);
  assert.equal(bootstrap.status, 200);
  const initial = await bootstrap.json() as { csrf_token: string; boundary: string; watchlists: unknown[] };
  assert.equal(initial.boundary, "NON_RAB1_RESEARCH_ONLY");
  assert.equal(initial.watchlists.length, 1);

  const payload = {
    record_type: "THESIS",
    instrument_id: "EQUITY_AAPL",
    title: "Services margin durability",
    body: "Invalidate if the declared filing condition fails.",
    status: "DRAFT",
    confidence: 55,
    tags: ["quality", "margin"],
    source_url: "https://www.sec.gov/",
    source_published_at: null,
    source_accessed_at: "2026-08-13T08:00:00.000Z",
    due_at: null,
  };
  const created = await handleResearchApi(writeRequest("/api/research/v1/records", "POST", initial.csrf_token, payload), env, identity);
  assert.equal(created.status, 201);
  const createdRecord = (await created.json() as { record: { record_id: string; revision: number } }).record;
  assert.equal(createdRecord.revision, 1);

  const updated = await handleResearchApi(writeRequest(`/api/research/v1/records/${createdRecord.record_id}`, "PUT", initial.csrf_token, { ...payload, status: "ACTIVE", revision: 1 }), env, identity);
  assert.equal(updated.status, 200);
  assert.equal((await updated.json() as { record: { revision: number } }).record.revision, 2);

  const stale = await handleResearchApi(writeRequest(`/api/research/v1/records/${createdRecord.record_id}`, "PUT", initial.csrf_token, { ...payload, revision: 1 }), env, identity);
  assert.equal(stale.status, 409);
  assert.deepEqual(await stale.json(), { error: "REVISION_CONFLICT" });

  const revisions = await handleResearchApi(new Request(`https://founder.example.test/api/research/v1/records/${createdRecord.record_id}/revisions`), env, identity);
  assert.equal(revisions.status, 200);
  assert.equal((await revisions.json() as { revisions: unknown[] }).revisions.length, 2);

  const otherIdentity = { ...identity, subject: "different-founder" };
  const otherBootstrap = await handleResearchApi(new Request("https://founder.example.test/api/research/v1/bootstrap"), env, otherIdentity);
  const otherToken = (await otherBootstrap.json() as { csrf_token: string }).csrf_token;
  const crossOwner = await handleResearchApi(writeRequest(`/api/research/v1/records/${createdRecord.record_id}`, "PUT", otherToken, { ...payload, revision: 2 }), env, otherIdentity);
  assert.equal(crossOwner.status, 409);
});

test("crypto dossier exposes live metadata and true 24-hour return semantics", async () => {
  const db = new SqliteD1();
  const env = {
    DELTAGRID_SYSTEM_DB: db,
    DELTAGRID_RESEARCH_CSRF_KEY: "c".repeat(64),
  };

  const now = "2026-08-14T00:00:00.000Z";

  db.database.prepare(
    `UPDATE research_provider_state
     SET status = 'OPERATIONAL',
         detail_code = 'COLLECTION_SUCCEEDED',
         last_attempt_at = ?,
         last_success_at = ?,
         next_due_at = ?,
         updated_at = ?
     WHERE provider_id = 'COINBASE_EXCHANGE'
       AND instrument_id = 'CRYPTO_BTC_USD'`,
  ).run(now, now, "2026-08-14T01:00:00.000Z", now);

  const insert = db.database.prepare(
    `INSERT INTO research_price_observations (
      instrument_id, observed_at, available_at, interval,
      open, high, low, close, volume, adjusted,
      source_sha256, boundary, authority_effect
    ) VALUES (
      ?, ?, ?, 'HOUR',
      ?, ?, ?, ?, ?, 0,
      ?, 'NON_RAB1_RESEARCH_ONLY', 'NONE'
    )`,
  );

  const closes: number[] = [];

  for (let index = 0; index < 25; index += 1) {
    const observedAt = new Date(
      Date.UTC(2026, 7, 13, index),
    ).toISOString();

    const close =
      100 + index + (index % 2 === 0 ? 2 : -2);

    closes.push(close);

    insert.run(
      "CRYPTO_BTC_USD",
      observedAt,
      observedAt,
      close,
      close,
      close,
      close,
      1,
      "a".repeat(64),
    );
  }

  const response = await handleResearchApi(
    new Request(
      "https://founder.example.test/api/research/v1/instruments/CRYPTO_BTC_USD",
    ),
    env,
    identity,
  );

  assert.equal(response.status, 200);

  const dossier = await response.json() as {
    instrument: {
      status: string;
      detail_code: string;
      latest_interval: string;
      latest_close: number;
      latest_observed_at: string;
    };
    metrics: {
      return_1d: number | null;
      realized_volatility: number | null;
    };
  };

  assert.equal(dossier.instrument.status, "OPERATIONAL");
  assert.equal(
    dossier.instrument.detail_code,
    "COLLECTION_SUCCEEDED",
  );
  assert.equal(dossier.instrument.latest_interval, "HOUR");
  assert.equal(
    dossier.instrument.latest_close,
    closes.at(-1),
  );

  assert.equal(
    dossier.metrics.return_1d,
    closes.at(-1)! / closes[0] - 1,
  );

  assert.ok(
    dossier.metrics.realized_volatility !== null &&
      dossier.metrics.realized_volatility > 0,
  );
});

test("research API exposes the founder intelligence brief as a read-only endpoint", async () => {
  const db = new SqliteD1();

  const env = {
    DELTAGRID_SYSTEM_DB: db,
    DELTAGRID_RESEARCH_CSRF_KEY:
      "c".repeat(64),
  };

  const response =
    await handleResearchApi(
      new Request(
        "https://founder.example.test/api/research/v1/brief",
      ),
      env,
      identity,
    );

  assert.equal(
    response.status,
    200,
  );

  const payload =
    await response.json() as {
      brief: {
        boundary: string;
        authority_effect: string;
        coverage: {
          market_total: number;
        };
        priorities: unknown[];
      };
    };

  assert.equal(
    payload.brief.boundary,
    "NON_RAB1_RESEARCH_ONLY",
  );

  assert.equal(
    payload.brief.authority_effect,
    "NONE",
  );

  assert.equal(
    payload.brief.coverage.market_total,
    8,
  );

  assert.equal(
    Array.isArray(
      payload.brief.priorities,
    ),
    true,
  );
});

test("research API rejects unknown write fields and cross-origin requests", async () => {
  const db = new SqliteD1();
  const env = { DELTAGRID_SYSTEM_DB: db, DELTAGRID_RESEARCH_CSRF_KEY: "c".repeat(64) };
  const bootstrap = await handleResearchApi(new Request("https://founder.example.test/api/research/v1/bootstrap"), env, identity);
  const token = (await bootstrap.json() as { csrf_token: string }).csrf_token;
  const invalid = await handleResearchApi(writeRequest("/api/research/v1/records", "POST", token, {
    record_type: "NOTE", title: "Note", body: "", status: "DRAFT", tags: [], protected_market_value: 100,
  }), env, identity);
  assert.equal(invalid.status, 400);
  const invalidBody = await invalid.json() as { error: string; request_id: string };
  assert.equal(invalidBody.error, "INVALID_RECORD_SHAPE");
  assert.match(invalidBody.request_id, /^[0-9a-f-]{36}$/u);

  const crossOrigin = new Request("https://founder.example.test/api/research/v1/records", {
    method: "POST",
    headers: { origin: "https://attacker.example", "sec-fetch-site": "cross-site", "content-type": "application/json", "x-deltagrid-csrf": token },
    body: "{}",
  });
  assert.equal((await handleResearchApi(crossOrigin, env, identity)).status, 403);
});

function writeRequest(path: string, method: string, token: string, body: unknown): Request {
  return new Request(`https://founder.example.test${path}`, {
    method,
    headers: {
      origin: "https://founder.example.test",
      "sec-fetch-site": "same-origin",
      "content-type": "application/json",
      "x-deltagrid-csrf": token,
    },
    body: JSON.stringify(body),
  });
}
