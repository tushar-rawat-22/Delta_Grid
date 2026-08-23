import assert from "node:assert/strict";
import test from "node:test";
import { ACTION_IDS } from "../founder/contracts.ts";
import {
  completeCommand,
  startCommand,
  type D1DatabaseLike,
  type D1ResultLike,
  type D1StatementLike,
} from "../founder/database.ts";
import { createFounderHandler, type FounderSystemEnv } from "../founder/worker.ts";

const identity = {
  subject: "founder-subject",
  email: "founder@example.test",
  expiresAt: 1_800_000_000,
};
const accept = async () => identity;
const reject = async () => {
  throw new Error("rejected");
};
const acceptAgent = async () => ({ commonName: "unit.access", agentId: "unit-agent" });

class FakeStatement implements D1StatementLike {
  values: unknown[] = [];
  private readonly query: string;
  private readonly writes: string[];

  constructor(query: string, writes: string[]) {
    this.query = query;
    this.writes = writes;
  }

  bind(...values: unknown[]): D1StatementLike {
    this.values = values;
    return this;
  }

  async first<T>(): Promise<T | null> {
    if (this.query.includes("SELECT COUNT(*)")) {
      return { commands: 0, requested: 0, executing: 0, receipts: 0, providers: 2, instruments: 2 } as T;
    }
    return null;
  }

  async run<T>(): Promise<D1ResultLike<T>> {
    if (/INSERT|UPDATE/u.test(this.query)) this.writes.push(this.query);
    return { success: true, results: [], meta: { changes: 1 } };
  }

  async all<T>(): Promise<D1ResultLike<T>> {
    return { success: true, results: [], meta: { changes: 0 } };
  }
}

class FakeDb implements D1DatabaseLike {
  writes: string[] = [];
  batchCalls = 0;

  prepare(query: string): D1StatementLike {
    return new FakeStatement(query, this.writes);
  }

  async batch<T>(statements: D1StatementLike[]): Promise<D1ResultLike<T>[]> {
    this.batchCalls += 1;
    return Promise.all(statements.map((statement) => statement.run<T>()));
  }
}

class FailingCommandAuditDb extends FakeDb {
  override async batch<T>(_statements: D1StatementLike[]): Promise<D1ResultLike<T>[]> {
    this.batchCalls += 1;
    return [
      { success: true, results: [], meta: { changes: 1 } },
      { success: false, results: [], meta: { changes: 0 } },
    ];
  }
}

function testEnv(db: FakeDb = new FakeDb()): FounderSystemEnv & { DELTAGRID_SYSTEM_DB: FakeDb } {
  return {
    DELTAGRID_SYSTEM_DB: db,
    DELTAGRID_CORE_COMMIT: "d94441f2f32fd8edc7b416beecd88b2b087d01a9",
    DELTAGRID_AUTHORITY_STATE: "NONE",
    DELTAGRID_AGENT_HMAC_KEY: "k".repeat(64),
    DELTAGRID_RESEARCH_CSRF_KEY: "r".repeat(64),
    ASSETS: { fetch: async () => new Response("<!doctype html><title>Research</title>", { headers: { "content-type": "text/html" } }) },
  };
}

test("founder GET and HEAD routes are authenticated and expose no authority", async () => {
  const handle = createFounderHandler(accept);
  const env = testEnv();
  const response = await handle(new Request("https://founder.example.test/founder/status"), env);
  assert.equal(response.status, 200);
  const body = await response.text();
  assert.match(body, /authenticated founder control plane/u);
  assert.match(body, /Trading\/capital authority:<\/strong> NONE/u);
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
  assert.equal(response.headers.get("x-frame-options"), "DENY");

  const head = await handle(new Request("https://founder.example.test/founder/security", { method: "HEAD" }), env);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), "");
});

test("missing or rejected Access identity returns generic 403", async () => {
  const handle = createFounderHandler(reject);
  const request = new Request("https://founder.example.test/founder", {
    headers: { "cf-access-jwt-assertion": "raw-secret-token" },
  });
  const response = await handle(request, testEnv());
  assert.equal(response.status, 403);
  const body = await response.text();
  assert.equal(body, "Forbidden");
  assert.doesNotMatch(body, /raw-secret-token|rejected|founder@example/u);
});

test("research UI revalidates founder identity before serving every private asset", async () => {
  const allowed = await createFounderHandler(accept)(new Request("https://founder.example.test/research/assets/app.js"), testEnv());
  assert.equal(allowed.status, 200);
  assert.match(allowed.headers.get("content-security-policy") ?? "", /connect-src 'self'/u);
  assert.equal(allowed.headers.get("cache-control"), "private, no-store, max-age=0");

  const denied = await createFounderHandler(reject)(new Request("https://founder.example.test/research"), testEnv());
  assert.equal(denied.status, 403);
  assert.equal(await denied.text(), "Forbidden");
});

test("research writes reject missing same-origin CSRF proof before database mutation", async () => {
  const env = testEnv();
  const response = await createFounderHandler(accept)(new Request("https://founder.example.test/api/research/v1/records", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title: "unsafe" }),
  }), env);
  assert.equal(response.status, 403);
  assert.deepEqual(await response.json(), { error: "REQUEST_INTEGRITY_FAILED" });
  assert.equal(env.DELTAGRID_SYSTEM_DB.writes.length, 0);
});

test("only the exact founder action route accepts POST", async () => {
  const handle = createFounderHandler(accept);
  for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
    const response = await handle(new Request("https://founder.example.test/founder", { method }), testEnv());
    assert.equal(response.status, 405, method);
    assert.equal(response.headers.get("allow"), "GET, HEAD, POST");
  }

  const unknown = await handle(new Request("https://founder.example.test/founder/arbitrary"), testEnv());
  assert.equal(unknown.status, 404);
});

test("founder response never exposes raw identity claims", async () => {
  const handle = createFounderHandler(accept);
  const response = await handle(new Request("https://founder.example.test/founder"), testEnv());
  const body = await response.text();
  assert.doesNotMatch(body, /founder@example\.test|founder-subject/u);
});

test("fixed action request requires same-origin form and exact confirmation", async () => {
  const handle = createFounderHandler(accept);
  const env = testEnv();
  const action = ACTION_IDS[0];
  const accepted = await handle(new Request("https://founder.example.test/founder/actions", {
    method: "POST",
    headers: {
      origin: "https://founder.example.test",
      "sec-fetch-site": "same-origin",
      "content-type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ action, confirmation: `REQUEST ${action}` }),
  }), env);
  assert.equal(accepted.status, 303);
  assert.equal(accepted.headers.get("location"), "/founder/actions");
  assert.equal(env.DELTAGRID_SYSTEM_DB.batchCalls, 1);
  assert.ok(env.DELTAGRID_SYSTEM_DB.writes.some((query) => query.includes("founder_command_requests")));
  assert.ok(env.DELTAGRID_SYSTEM_DB.writes.some((query) => query.includes("founder_security_events")));

  const rejected = await handle(new Request("https://founder.example.test/founder/actions", {
    method: "POST",
    headers: {
      origin: "https://attacker.example.test",
      "sec-fetch-site": "cross-site",
      "content-type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ action, confirmation: `REQUEST ${action}` }),
  }), testEnv());
  assert.equal(rejected.status, 403);
});

test("command creation fails closed when the atomic command-audit batch is incomplete", async () => {
  const handle = createFounderHandler(accept);
  const db = new FailingCommandAuditDb();
  const action = ACTION_IDS[0];
  const response = await handle(new Request("https://founder.example.test/founder/actions", {
    method: "POST",
    headers: {
      origin: "https://founder.example.test",
      "sec-fetch-site": "same-origin",
      "content-type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ action, confirmation: `REQUEST ${action}` }),
  }), testEnv(db));
  assert.equal(response.status, 503);
  assert.equal(db.batchCalls, 1);
  assert.ok(db.writes.some((query) => query.includes("founder_security_events")));
  assert.ok(!db.writes.some((query) => query.includes("founder_command_requests")));
});

test("agent endpoint is POST-only and independently authenticated", async () => {
  const handle = createFounderHandler(accept, acceptAgent);
  const get = await handle(new Request("https://founder.example.test/agent/v1/claim"), testEnv());
  assert.equal(get.status, 405);
  const claim = await handle(new Request("https://founder.example.test/agent/v1/claim", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      authority_state: "NONE",
      core_commit: "d94441f2f32fd8edc7b416beecd88b2b087d01a9",
    }),
  }), testEnv());
  assert.equal(claim.status, 200);
  assert.deepEqual(await claim.json(), { command: null });
});

test("agent records metadata-only evidence and provider health", async () => {
  const handle = createFounderHandler(accept, acceptAgent);
  const env = testEnv();
  const evidence = {
    authority_state: "NONE",
    available_at: "2026-08-13T00:00:01.000Z",
    content_length: 1234,
    envelope_id: "00000000-0000-4000-8000-000000000001",
    instrument_id: "US_EQUITY_AAPL_PRIVATE_PILOT",
    local_receipt_sha256: "1".repeat(64),
    observed_at: "2026-08-13T00:00:00.000Z",
    payload_sha256: "2".repeat(64),
    private_only: true,
    provider_id: "SEC_EDGAR_PRIVATE_PILOT",
    provider_record_date: "2026-08-12",
    schema_version: 1,
  };
  const response = await handle(new Request("https://founder.example.test/agent/v1/evidence", {
    method: "POST",
    body: JSON.stringify(evidence),
  }), env);
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), {
    status: "EVIDENCE_RECORDED",
    envelope_id: evidence.envelope_id,
  });
  assert.ok(env.DELTAGRID_SYSTEM_DB.writes.some((query) => query.includes("temporal_evidence_envelopes")));

  const status = await handle(new Request("https://founder.example.test/agent/v1/status", {
    method: "POST",
    body: JSON.stringify({
      authority_state: "NONE",
      detail_code: "CAPTURE_REPLAY_AND_ROLLBACK_VERIFIED",
      latest_envelope_id: evidence.envelope_id,
      local_receipt_sha256: "3".repeat(64),
      payload_sha256: evidence.payload_sha256,
      provider_id: evidence.provider_id,
      receipt_id: "00000000-0000-4000-8000-000000000002",
      recorded_at: "2026-08-13T00:00:02.000Z",
      status: "OPERATIONAL",
    }),
  }), env);
  assert.equal(status.status, 201);
  assert.ok(env.DELTAGRID_SYSTEM_DB.writes.some((query) => query.includes("provider_health_receipts")));
});

test("agent evidence route rejects market values and generic metadata", async () => {
  const handle = createFounderHandler(accept, acceptAgent);
  const response = await handle(new Request("https://founder.example.test/agent/v1/evidence", {
    method: "POST",
    body: JSON.stringify({
      authority_state: "NONE",
      available_at: "2026-08-13T00:00:01.000Z",
      content_length: 1234,
      envelope_id: "00000000-0000-4000-8000-000000000001",
      instrument_id: "US_EQUITY_AAPL_PRIVATE_PILOT",
      local_receipt_sha256: "1".repeat(64),
      market_value: "999999999",
      observed_at: "2026-08-13T00:00:00.000Z",
      payload_sha256: "2".repeat(64),
      private_only: true,
      provider_id: "SEC_EDGAR_PRIVATE_PILOT",
      provider_record_date: "2026-08-12",
      schema_version: 1,
    }),
  }), testEnv());
  assert.equal(response.status, 400);
  assert.deepEqual(await response.json(), { error: "EVIDENCE_METADATA_INVALID" });
});

test("D1 returned rows prove lifecycle writes when changes metadata is absent", async () => {
  const returnedRowStatement: D1StatementLike = {
    bind: () => returnedRowStatement,
    first: async <T>() => null as T | null,
    all: async <T>() => ({ success: true, results: [] as T[] }),
    run: async <T>() => ({ success: true, results: [{ command_id: "command" }] as T[] }),
  };
  const returnedReceiptStatement: D1StatementLike = {
    ...returnedRowStatement,
    bind: () => returnedReceiptStatement,
    run: async <T>() => ({ success: true, results: [{ receipt_id: "receipt" }] as T[] }),
  };
  let prepared = 0;
  const db: D1DatabaseLike = {
    prepare: () => (prepared++ === 0 ? returnedRowStatement : returnedReceiptStatement),
    batch: async <T>(statements: D1StatementLike[]) => Promise.all(statements.map((statement) => statement.run<T>())),
  };
  assert.equal(await startCommand(db, "command", "unit-agent", new Date().toISOString()), true);

  prepared = 0;
  assert.equal(await completeCommand(db, {
    commandId: "command",
    agentId: "unit-agent",
    status: "SUCCEEDED",
    terminalCode: "ACTION_COMPLETED",
    startedAt: new Date().toISOString(),
    completedAt: new Date().toISOString(),
    durationMs: 1,
    outputSha256: "0".repeat(64),
    localReceiptSha256: "1".repeat(64),
  }), true);
});
