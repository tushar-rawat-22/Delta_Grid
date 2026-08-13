import { verifyFounderRequest, type FounderAccessEnv, type FounderIdentity } from "./auth.ts";
import { verifyAgentRequest, type AgentAccessEnv, type AgentIdentity } from "./agent-auth.ts";
import {
  ACTION_IDS,
  AUTHORITY_STATE,
  COMMAND_SCHEMA_VERSION,
  COMMAND_TTL_SECONDS,
  canonicalJson,
  isActionId,
  type CommandRecord,
} from "./contracts.ts";
import { commandIntegrityProof, sha256Hex } from "./crypto.ts";
import { handleResearchApi } from "./research-api.ts";
import { collectDueResearchProviders } from "./research-providers.ts";
import {
  claimCommand,
  completeCommand,
  expireStaleCommands,
  insertCommand,
  insertEvidenceEnvelope,
  insertProviderHealth,
  insertSecurityEvent,
  listRecentCommands,
  startCommand,
  systemCounts,
  type D1DatabaseLike,
  type ReceiptInput,
} from "./database.ts";

type FounderVerifier = (request: Request, env: FounderAccessEnv) => Promise<FounderIdentity>;
type AgentVerifier = (request: Request, body: string, env: AgentAccessEnv) => Promise<AgentIdentity>;

export type FounderSystemEnv = FounderAccessEnv & AgentAccessEnv & {
  DELTAGRID_SYSTEM_DB?: D1DatabaseLike;
  DELTAGRID_CORE_COMMIT?: string;
  DELTAGRID_AUTHORITY_STATE?: string;
  DELTAGRID_RESEARCH_CSRF_KEY?: string;
  ALPHA_VANTAGE_API_KEY?: string;
  FRED_API_KEY?: string;
  ASSETS?: { fetch(request: Request): Promise<Response> };
};

const FOUNDER_PATHS = new Set([
  "/founder",
  "/founder/status",
  "/founder/security",
  "/founder/actions",
  "/founder/receipts",
]);
const AGENT_PATHS = new Set([
  "/agent/v1/claim",
  "/agent/v1/start",
  "/agent/v1/complete",
  "/agent/v1/evidence",
  "/agent/v1/status",
]);
const SECURITY_HEADERS = {
  "cache-control": "no-store, max-age=0",
  "content-security-policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; style-src 'unsafe-inline'",
  "content-type": "text/html; charset=utf-8",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "referrer-policy": "no-referrer",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "x-robots-tag": "noindex, nofollow",
} as const;

export function createFounderHandler(
  verifyFounder: FounderVerifier = verifyFounderRequest,
  verifyAgent: AgentVerifier = verifyAgentRequest,
) {
  return async function handleFounderRequest(request: Request, env: FounderSystemEnv): Promise<Response> {
    const url = new URL(request.url);
    if (AGENT_PATHS.has(url.pathname)) return handleAgentRoute(request, env, verifyAgent);
    const researchApi = url.pathname === "/api/research/v1" || url.pathname.startsWith("/api/research/v1/");
    const researchUi = url.pathname === "/research" || url.pathname.startsWith("/research/");
    if (!FOUNDER_PATHS.has(url.pathname) && !researchApi && !researchUi) return textResponse("Not Found", 404);

    let identity: FounderIdentity;
    try {
      identity = await verifyFounder(request, env);
    } catch {
      return textResponse("Forbidden", 403);
    }

    if (researchApi) return handleResearchApi(request, env, identity);
    if (researchUi) return handleResearchAsset(request, env);

    if (request.method === "POST" && url.pathname === "/founder/actions") {
      return handleCommandCreation(request, env, identity);
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      return textResponse("Method Not Allowed", 405, { allow: "GET, HEAD, POST" });
    }

    try {
      const body = await renderFounderPage(url.pathname, identity, env);
      return new Response(request.method === "HEAD" ? null : body, { status: 200, headers: SECURITY_HEADERS });
    } catch {
      return textResponse("Service Unavailable", 503);
    }
  };
}

const handleFounderRequest = createFounderHandler();

const founderWorker = {
  fetch(request: Request, env: FounderSystemEnv): Promise<Response> {
    return handleFounderRequest(request, env);
  },
  scheduled(controller: { scheduledTime: number }, env: FounderSystemEnv, ctx: { waitUntil(promise: Promise<unknown>): void }): void {
    ctx.waitUntil(collectDueResearchProviders(env, controller.scheduledTime).catch((error: unknown) => {
      console.error(JSON.stringify({
        event: "research_scheduled_failure",
        error_code: error instanceof Error && /^[A-Z0-9_]{3,96}$/u.test(error.message) ? error.message : "UNCLASSIFIED_FAILURE",
        boundary: "NON_RAB1_RESEARCH_ONLY",
        authority_effect: "NONE",
      }));
    }));
  },
};

export default founderWorker;

async function handleCommandCreation(
  request: Request,
  env: FounderSystemEnv,
  identity: FounderIdentity,
): Promise<Response> {
  const db = requiredDb(env);
  const signingKey = requiredSigningKey(env);
  const url = new URL(request.url);
  const origin = request.headers.get("origin");
  const fetchSite = request.headers.get("sec-fetch-site");
  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (origin !== url.origin || (fetchSite !== "same-origin" && fetchSite !== "none")) {
    await insertSecurityEvent(db, "COMMAND_CREATE", "FOUNDER", "DENY", "ORIGIN_CHECK_FAILED");
    return textResponse("Forbidden", 403);
  }
  if (contentType !== "application/x-www-form-urlencoded") return textResponse("Unsupported Media Type", 415);
  const rawBody = await request.text();
  if (rawBody.length > 2048) return textResponse("Payload Too Large", 413);
  const form = new URLSearchParams(rawBody);
  const action = form.get("action") ?? "";
  const confirmation = form.get("confirmation") ?? "";
  if (!isActionId(action) || confirmation !== `REQUEST ${action}` || [...form.keys()].some((key) => !["action", "confirmation"].includes(key))) {
    await insertSecurityEvent(db, "COMMAND_CREATE", "FOUNDER", "DENY", "COMMAND_VALIDATION_FAILED");
    return textResponse("Invalid command request", 400);
  }

  const coreCommit = requiredCoreCommit(env);
  const requestedAt = new Date();
  const expiresAt = new Date(requestedAt.getTime() + COMMAND_TTL_SECONDS * 1000);
  const founderUserId = await sha256Hex(identity.subject ?? identity.email);
  const parameterJson = canonicalJson({});
  const base = {
    command_id: crypto.randomUUID(),
    schema_version: COMMAND_SCHEMA_VERSION,
    requested_action_id: action,
    founder_user_id: founderUserId,
    requested_at: requestedAt.toISOString(),
    expires_at: expiresAt.toISOString(),
    one_use_nonce: crypto.randomUUID().replaceAll("-", ""),
    expected_core_commit: coreCommit,
    expected_authority_state: AUTHORITY_STATE,
    parameter_json: parameterJson,
    parameter_hash: await sha256Hex(parameterJson),
    canonical_request_hash: "",
  };
  base.canonical_request_hash = await sha256Hex(canonicalJson({ ...base, canonical_request_hash: undefined }));
  const command = {
    ...base,
    integrity_proof: await commandIntegrityProof(base, signingKey),
  };
  try {
    await insertCommand(db, command);
    await insertSecurityEvent(db, "COMMAND_CREATE", "FOUNDER", "ALLOW", "FIXED_ACTION_ACCEPTED");
  } catch {
    await insertSecurityEvent(db, "COMMAND_CREATE", "FOUNDER", "ERROR", "COMMAND_INSERT_FAILED");
    return textResponse("Command could not be queued", 503);
  }
  return new Response(null, {
    status: 303,
    headers: { ...SECURITY_HEADERS, location: "/founder/actions" },
  });
}

async function handleAgentRoute(
  request: Request,
  env: FounderSystemEnv,
  verifyAgent: AgentVerifier,
): Promise<Response> {
  if (request.method !== "POST") return jsonResponse({ error: "METHOD_NOT_ALLOWED" }, 405, { allow: "POST" });
  const rawBody = await request.text();
  if (rawBody.length > 8192) return jsonResponse({ error: "PAYLOAD_TOO_LARGE" }, 413);
  const db = requiredDb(env);
  let agent: AgentIdentity;
  try {
    agent = await verifyAgent(request, rawBody, env);
  } catch (error) {
    const reason = error instanceof Error && /^AGENT_[A-Z0-9_]+$/u.test(error.message)
      ? error.message
      : "AGENT_AUTHENTICATION_FAILED";
    try {
      await insertSecurityEvent(db, "AGENT_AUTHENTICATION", "AGENT", "DENY", reason);
    } catch {
      // Authentication remains fail-closed even if its audit write is unavailable.
    }
    return jsonResponse({ error: "AGENT_AUTHENTICATION_FAILED" }, 403);
  }
  const url = new URL(request.url);
  const now = new Date().toISOString();
  let payload: Record<string, unknown>;
  try {
    payload = rawBody ? JSON.parse(rawBody) as Record<string, unknown> : {};
  } catch {
    return jsonResponse({ error: "INVALID_JSON" }, 400);
  }

  try {
    await expireStaleCommands(db, now);
    if (url.pathname === "/agent/v1/claim") {
      if (Object.keys(payload).length !== 2 || payload.core_commit !== requiredCoreCommit(env) || payload.authority_state !== AUTHORITY_STATE) {
        return jsonResponse({ error: "AGENT_STATE_MISMATCH" }, 409);
      }
      const command = await claimCommand(db, agent.agentId, requiredCoreCommit(env), AUTHORITY_STATE, now);
      return jsonResponse({ command: command ? publicAgentCommand(command) : null }, 200);
    }
    if (url.pathname === "/agent/v1/start") {
      const commandId = exactCommandId(payload);
      const started = await startCommand(db, commandId, agent.agentId, now);
      return started ? jsonResponse({ status: "EXECUTING" }, 200) : jsonResponse({ error: "COMMAND_START_REJECTED" }, 409);
    }
    if (url.pathname === "/agent/v1/evidence") {
      let envelope: import("./database.ts").EvidenceEnvelopeInput;
      try {
        envelope = exactEvidenceEnvelope(payload);
      } catch {
        return jsonResponse({ error: "EVIDENCE_METADATA_INVALID" }, 400);
      }
      const inserted = await insertEvidenceEnvelope(db, { ...envelope, receivedAt: now });
      return inserted
        ? jsonResponse({ status: "EVIDENCE_RECORDED", envelope_id: envelope.envelopeId }, 201)
        : jsonResponse({ error: "EVIDENCE_REPLAY_OR_REJECTED" }, 409);
    }
    if (url.pathname === "/agent/v1/status") {
      let receipt: import("./database.ts").ProviderHealthInput;
      try {
        receipt = exactProviderHealth(payload);
      } catch {
        return jsonResponse({ error: "PROVIDER_STATUS_INVALID" }, 400);
      }
      const inserted = await insertProviderHealth(db, receipt);
      return inserted
        ? jsonResponse({ status: "PROVIDER_STATUS_RECORDED", receipt_id: receipt.receiptId }, 201)
        : jsonResponse({ error: "PROVIDER_STATUS_REPLAY_OR_REJECTED" }, 409);
    }
    const receipt = exactReceipt(payload, agent.agentId);
    const completed = await completeCommand(db, receipt);
    return completed ? jsonResponse({ status: receipt.status }, 200) : jsonResponse({ error: "COMMAND_COMPLETION_REJECTED" }, 409);
  } catch {
    await insertSecurityEvent(db, "AGENT_REQUEST", "AGENT", "ERROR", "AGENT_ROUTE_FAILURE");
    return jsonResponse({ error: "SERVICE_UNAVAILABLE" }, 503);
  }
}

async function renderFounderPage(pathname: string, identity: FounderIdentity, env: FounderSystemEnv): Promise<string> {
  const expiry = identity.expiresAt ? new Date(identity.expiresAt * 1000).toISOString() : "Access-managed";
  if (pathname === "/founder/actions" || pathname === "/founder/receipts") {
    const commands = await listRecentCommands(requiredDb(env));
    return page("Founder actions", `${renderNav()}
      <p class="muted">Only fixed, pre-reviewed actions are accepted. Requests expire in five minutes.</p>
      ${pathname === "/founder/actions" ? renderActionForms() : ""}
      ${renderCommands(commands)}`);
  }
  if (pathname === "/founder/security") {
    const counts = await systemCounts(requiredDb(env));
    return page("Founder security", `${renderNav()}<section>
      <p><strong>Human identity:</strong> Cloudflare Access JWT, exact founder identity, independent MFA.</p>
      <p><strong>Machine identity:</strong> separate path-scoped Access service credential plus signed, replay-protected requests.</p>
      <p><strong>Authority:</strong> NONE.</p>
      <p><strong>Audit:</strong> ${escapeHtml(String(counts.commands))} commands · ${escapeHtml(String(counts.receipts))} durable receipts.</p>
      <p><strong>Market foundation:</strong> ${escapeHtml(String(counts.providers))} private providers · ${escapeHtml(String(counts.instruments))} private pilot instruments.</p>
    </section>`);
  }
  if (pathname === "/founder/status") {
    const counts = await systemCounts(requiredDb(env));
    return page("Founder status", `${renderNav()}<section>
      <p><strong>Session expiry:</strong> ${escapeHtml(expiry)}</p>
      <p><strong>Queue:</strong> ${escapeHtml(String(counts.requested))} requested · ${escapeHtml(String(counts.executing))} executing.</p>
      <p><strong>Private pilot:</strong> ${escapeHtml(String(counts.evidence_envelopes))} metadata envelopes · ${escapeHtml(String(counts.operational_receipts))} operational receipts.</p>
      <p><strong>Core pin:</strong> ${escapeHtml(requiredCoreCommit(env))}</p>
      <p><strong>Trading/capital authority:</strong> NONE.</p>
    </section>`);
  }
  return page("Founder control plane", `${renderNav()}<section>
    <p><strong>Identity:</strong> verified by Cloudflare Access JWT and exact founder-email match.</p>
    <p><strong>Session expiry:</strong> ${escapeHtml(expiry)}</p>
    <p><strong>Commands:</strong> fixed registry, server validated, outbound agent only.</p>
    <p><strong>Trading/capital authority:</strong> NONE.</p>
    <p><strong>Private market payload exposure:</strong> NONE.</p>
  </section>`);
}

const PROVIDER_INSTRUMENTS = {
  SEC_EDGAR_PRIVATE_PILOT: "US_EQUITY_AAPL_PRIVATE_PILOT",
  US_TREASURY_FISCALDATA_PRIVATE_PILOT: "US_MACRO_TREASURY_DEBT_PRIVATE_PILOT",
} as const;

function exactEvidenceEnvelope(payload: Record<string, unknown>): import("./database.ts").EvidenceEnvelopeInput {
  const keys = [
    "authority_state", "available_at", "content_length", "envelope_id", "instrument_id",
    "local_receipt_sha256", "observed_at", "payload_sha256", "private_only",
    "provider_id", "provider_record_date", "schema_version",
  ];
  if (Object.keys(payload).sort().join(",") !== keys.sort().join(",")) throw new Error("EVIDENCE_SHAPE_INVALID");
  const providerId = typeof payload.provider_id === "string" ? payload.provider_id : "";
  const instrumentId = PROVIDER_INSTRUMENTS[providerId as keyof typeof PROVIDER_INSTRUMENTS];
  if (!instrumentId || payload.instrument_id !== instrumentId) throw new Error("EVIDENCE_PROVIDER_INVALID");
  if (payload.schema_version !== 1 || payload.private_only !== true || payload.authority_state !== AUTHORITY_STATE) {
    throw new Error("EVIDENCE_BOUNDARY_INVALID");
  }
  const envelopeId = exactUuid(payload.envelope_id, "EVIDENCE_ID_INVALID");
  const observedAt = exactIsoTime(payload.observed_at, "EVIDENCE_OBSERVED_AT_INVALID");
  const availableAt = exactIsoTime(payload.available_at, "EVIDENCE_AVAILABLE_AT_INVALID");
  if (availableAt < observedAt) throw new Error("EVIDENCE_TIME_ORDER_INVALID");
  if (typeof payload.payload_sha256 !== "string" || !/^[0-9a-f]{64}$/u.test(payload.payload_sha256)) throw new Error("EVIDENCE_HASH_INVALID");
  if (typeof payload.local_receipt_sha256 !== "string" || !/^[0-9a-f]{64}$/u.test(payload.local_receipt_sha256)) throw new Error("EVIDENCE_RECEIPT_HASH_INVALID");
  if (!Number.isInteger(payload.content_length) || Number(payload.content_length) < 2 || Number(payload.content_length) > 8_388_608) throw new Error("EVIDENCE_LENGTH_INVALID");
  if (typeof payload.provider_record_date !== "string" || !/^\d{4}-\d{2}-\d{2}$/u.test(payload.provider_record_date)) throw new Error("EVIDENCE_RECORD_DATE_INVALID");
  return {
    envelopeId,
    providerId,
    instrumentId,
    observedAt,
    availableAt,
    payloadSha256: payload.payload_sha256,
    contentLength: Number(payload.content_length),
    providerRecordDate: payload.provider_record_date,
    localReceiptSha256: payload.local_receipt_sha256,
    receivedAt: "",
  };
}

function exactProviderHealth(payload: Record<string, unknown>): import("./database.ts").ProviderHealthInput {
  const keys = [
    "authority_state", "detail_code", "latest_envelope_id", "local_receipt_sha256",
    "payload_sha256", "provider_id", "receipt_id", "recorded_at", "status",
  ];
  if (Object.keys(payload).sort().join(",") !== keys.sort().join(",")) throw new Error("PROVIDER_STATUS_SHAPE_INVALID");
  const providerId = typeof payload.provider_id === "string" ? payload.provider_id : "";
  if (!(providerId in PROVIDER_INSTRUMENTS) || payload.authority_state !== AUTHORITY_STATE) throw new Error("PROVIDER_STATUS_BOUNDARY_INVALID");
  if (!(payload.status === "OPERATIONAL" || payload.status === "DEGRADED" || payload.status === "FAILED")) throw new Error("PROVIDER_STATUS_INVALID");
  if (typeof payload.local_receipt_sha256 !== "string" || !/^[0-9a-f]{64}$/u.test(payload.local_receipt_sha256)) throw new Error("PROVIDER_STATUS_RECEIPT_HASH_INVALID");
  if (payload.payload_sha256 !== null && (typeof payload.payload_sha256 !== "string" || !/^[0-9a-f]{64}$/u.test(payload.payload_sha256))) throw new Error("PROVIDER_STATUS_PAYLOAD_HASH_INVALID");
  const latestEnvelopeId = payload.latest_envelope_id === null
    ? null
    : exactUuid(payload.latest_envelope_id, "PROVIDER_STATUS_ENVELOPE_INVALID");
  const payloadSha256 = payload.payload_sha256 === null ? null : payload.payload_sha256;
  if (typeof payload.detail_code !== "string" || !/^[A-Z0-9_]{3,96}$/u.test(payload.detail_code)) throw new Error("PROVIDER_STATUS_DETAIL_INVALID");
  return {
    receiptId: exactUuid(payload.receipt_id, "PROVIDER_STATUS_ID_INVALID"),
    providerId,
    recordedAt: exactIsoTime(payload.recorded_at, "PROVIDER_STATUS_TIME_INVALID"),
    status: payload.status,
    latestEnvelopeId,
    payloadSha256,
    localReceiptSha256: payload.local_receipt_sha256,
    detailCode: payload.detail_code,
  };
}

function exactUuid(value: unknown, code: string): string {
  if (typeof value !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u.test(value)) throw new Error(code);
  return value;
}

function exactIsoTime(value: unknown, code: string): string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(value) || Number.isNaN(Date.parse(value))) throw new Error(code);
  return value;
}

function renderActionForms(): string {
  return `<div class="grid">${ACTION_IDS.map((action) => `<form method="post" action="/founder/actions">
    <input type="hidden" name="action" value="${action}">
    <label>Type <code>REQUEST ${action}</code> to confirm
      <input type="text" name="confirmation" required autocomplete="off" spellcheck="false" pattern="REQUEST ${action}" aria-label="Confirm ${action}">
    </label>
    <button type="submit">${action.replaceAll("_", " ")}</button>
  </form>`).join("")}</div>`;
}

function renderCommands(commands: CommandRecord[]): string {
  if (commands.length === 0) return "<p>No commands have been requested.</p>";
  return `<table><thead><tr><th>Requested</th><th>Action</th><th>Status</th><th>Code</th></tr></thead><tbody>${commands.map((command) =>
    `<tr><td>${escapeHtml(command.requested_at)}</td><td>${escapeHtml(command.requested_action_id)}</td><td>${escapeHtml(command.status)}</td><td>${escapeHtml(command.terminal_code ?? "—")}</td></tr>`,
  ).join("")}</tbody></table>`;
}

function renderNav(): string {
  return `<nav><a href="/research">Research</a><a href="/founder">Home</a><a href="/founder/status">Status</a><a href="/founder/actions">Actions</a><a href="/founder/receipts">Receipts</a><a href="/founder/security">Security</a></nav>`;
}

function page(title: string, content: string): string {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(title)} · DeltaGrid</title></head>
  <body><main><p class="muted">DeltaGrid · authenticated founder control plane</p><h1>${escapeHtml(title)}</h1>${content}</main></body>
  <style>body{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#0b0d10;color:#e7e9ee;margin:0;padding:40px}main{max-width:980px;margin:auto}section,form,table{border:1px solid #2b3038;border-radius:8px}section{padding:20px}.muted{color:#89909b}nav{display:flex;gap:18px;margin:0 0 24px}a{color:#8ab4ff}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;margin:20px 0}form{padding:12px}label{display:grid;gap:8px;font-size:12px;color:#aeb4bf}code{overflow-wrap:anywhere;color:#d7e4ff}input{background:#0b0d10;color:#e7e9ee;border:1px solid #414957;border-radius:6px;padding:9px}button{width:100%;margin-top:10px;background:#171b22;color:#e7e9ee;border:1px solid #414957;border-radius:6px;padding:10px;cursor:pointer}table{width:100%;border-collapse:collapse;overflow:hidden}th,td{text-align:left;padding:10px;border-bottom:1px solid #2b3038;font-size:12px}</style></html>`;
}

function publicAgentCommand(command: CommandRecord): Record<string, unknown> {
  return {
    command_id: command.command_id,
    schema_version: command.schema_version,
    requested_action_id: command.requested_action_id,
    founder_user_id: command.founder_user_id,
    requested_at: command.requested_at,
    expires_at: command.expires_at,
    one_use_nonce: command.one_use_nonce,
    expected_core_commit: command.expected_core_commit,
    expected_authority_state: command.expected_authority_state,
    parameter_json: command.parameter_json,
    parameter_hash: command.parameter_hash,
    canonical_request_hash: command.canonical_request_hash,
    integrity_proof: command.integrity_proof,
  };
}

function exactCommandId(payload: Record<string, unknown>): string {
  if (Object.keys(payload).length !== 1 || typeof payload.command_id !== "string" || !/^[0-9a-f-]{36}$/u.test(payload.command_id)) {
    throw new Error("COMMAND_ID_INVALID");
  }
  return payload.command_id;
}

function exactReceipt(payload: Record<string, unknown>, agentId: string): ReceiptInput {
  const keys = ["command_id", "status", "terminal_code", "started_at", "completed_at", "duration_ms", "output_sha256", "local_receipt_sha256"];
  if (Object.keys(payload).sort().join(",") !== keys.sort().join(",")) throw new Error("RECEIPT_SHAPE_INVALID");
  if (typeof payload.command_id !== "string" || !/^[0-9a-f-]{36}$/u.test(payload.command_id)) throw new Error("RECEIPT_COMMAND_ID_INVALID");
  if (!(["SUCCEEDED", "FAILED", "REJECTED"] as unknown[]).includes(payload.status)) throw new Error("RECEIPT_STATUS_INVALID");
  if (typeof payload.terminal_code !== "string" || !/^[A-Z0-9_]{3,96}$/u.test(payload.terminal_code)) throw new Error("RECEIPT_CODE_INVALID");
  if (typeof payload.started_at !== "string" || typeof payload.completed_at !== "string") throw new Error("RECEIPT_TIME_INVALID");
  if (!Number.isInteger(payload.duration_ms) || Number(payload.duration_ms) < 0 || Number(payload.duration_ms) > 86_400_000) throw new Error("RECEIPT_DURATION_INVALID");
  if (typeof payload.output_sha256 !== "string" || !/^[0-9a-f]{64}$/u.test(payload.output_sha256)) throw new Error("RECEIPT_OUTPUT_HASH_INVALID");
  if (typeof payload.local_receipt_sha256 !== "string" || !/^[0-9a-f]{64}$/u.test(payload.local_receipt_sha256)) throw new Error("RECEIPT_LOCAL_HASH_INVALID");
  return {
    commandId: payload.command_id,
    agentId,
    status: payload.status as ReceiptInput["status"],
    terminalCode: payload.terminal_code,
    startedAt: payload.started_at,
    completedAt: payload.completed_at,
    durationMs: Number(payload.duration_ms),
    outputSha256: payload.output_sha256,
    localReceiptSha256: payload.local_receipt_sha256,
  };
}

function requiredDb(env: FounderSystemEnv): D1DatabaseLike {
  if (!env.DELTAGRID_SYSTEM_DB) throw new Error("SYSTEM_DATABASE_MISSING");
  return env.DELTAGRID_SYSTEM_DB;
}

function requiredCoreCommit(env: FounderSystemEnv): string {
  const value = env.DELTAGRID_CORE_COMMIT?.trim().toLowerCase();
  if (!value || !/^[0-9a-f]{40}$/u.test(value)) throw new Error("CORE_COMMIT_INVALID");
  if (env.DELTAGRID_AUTHORITY_STATE !== AUTHORITY_STATE) throw new Error("AUTHORITY_STATE_INVALID");
  return value;
}

function requiredSigningKey(env: FounderSystemEnv): string {
  const value = env.DELTAGRID_AGENT_HMAC_KEY;
  if (!value || value.length < 32) throw new Error("COMMAND_SIGNING_KEY_INVALID");
  return value;
}

async function handleResearchAsset(request: Request, env: FounderSystemEnv): Promise<Response> {
  if (request.method !== "GET" && request.method !== "HEAD") return textResponse("Method Not Allowed", 405, { allow: "GET, HEAD" });
  if (!env.ASSETS) return textResponse("Service Unavailable", 503);
  const sourceUrl = new URL(request.url);
  const lastSegment = sourceUrl.pathname.split("/").at(-1) ?? "";
  const assetUrl = new URL(sourceUrl);
  if (sourceUrl.pathname === "/research" || sourceUrl.pathname === "/research/" || !lastSegment.includes(".")) {
    assetUrl.pathname = "/research/index.html";
    assetUrl.search = "";
  }
  const assetRequest = new Request(assetUrl, { method: request.method, headers: request.headers });
  const asset = await env.ASSETS.fetch(assetRequest);
  if (!asset.ok) return textResponse("Not Found", 404);
  const headers = new Headers(asset.headers);
  headers.set("cache-control", "private, no-store, max-age=0");
  headers.set("content-security-policy", "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; connect-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; font-src 'self'");
  headers.set("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()");
  headers.set("referrer-policy", "no-referrer");
  headers.set("x-content-type-options", "nosniff");
  headers.set("x-frame-options", "DENY");
  headers.set("x-robots-tag", "noindex, nofollow");
  return new Response(request.method === "HEAD" ? null : asset.body, { status: asset.status, headers });
}

function textResponse(body: string, status: number, extra: Record<string, string> = {}): Response {
  return new Response(body, {
    status,
    headers: { ...SECURITY_HEADERS, "content-type": "text/plain; charset=utf-8", ...extra },
  });
}

function jsonResponse(body: Record<string, unknown>, status: number, extra: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...SECURITY_HEADERS, "content-type": "application/json; charset=utf-8", ...extra },
  });
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>'"]/gu, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character] ?? character);
}
