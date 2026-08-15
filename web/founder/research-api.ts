import type { FounderIdentity } from "./auth.ts";
import type { D1DatabaseLike } from "./database.ts";
import {
  createRecord,
  createWatchlist,
  ensureDefaultWatchlist,
  getInstrumentDossier,
  getMarketIntelligenceBrief,
  getPriceBars,
  listMacro,
  listProviderHealth,
  listRecordRevisions,
  listRecords,
  listResearchInstruments,
  listWatchlists,
  recentDashboard,
  replaceWatchlist,
  updateRecord,
  RESEARCH_AUTHORITY,
  RESEARCH_BOUNDARY,
  type ResearchRecord,
  type ResearchRecordInput,
} from "./research-database.ts";
import { compareSeries } from "./research-metrics.ts";
import {
  founderOwnerId,
  issueResearchCsrf,
  verifyResearchCsrf,
  verifySameOrigin,
  type ResearchSecurityEnv,
} from "./research-security.ts";

export type ResearchApiEnv = ResearchSecurityEnv & {
  DELTAGRID_SYSTEM_DB?: D1DatabaseLike;
};

const RECORD_TYPES = new Set(["NOTE", "THESIS", "EVIDENCE", "JOURNAL", "CATALYST", "RISK", "TASK"]);
const RECORD_STATUSES = new Set(["DRAFT", "ACTIVE", "WATCHING", "DONE", "ARCHIVED"]);
const API_HEADERS = {
  "cache-control": "no-store, max-age=0",
  "content-type": "application/json; charset=utf-8",
  "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "referrer-policy": "no-referrer",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "x-robots-tag": "noindex, nofollow",
} as const;

export async function handleResearchApi(
  request: Request,
  env: ResearchApiEnv,
  identity: FounderIdentity,
): Promise<Response> {
  const db = env.DELTAGRID_SYSTEM_DB;
  if (!db) return apiError("SERVICE_UNAVAILABLE", 503);
  const url = new URL(request.url);
  const path = url.pathname.slice("/api/research/v1".length) || "/";
  const isWrite = ["POST", "PUT", "PATCH", "DELETE"].includes(request.method);
  if (isWrite) {
    if (!verifySameOrigin(request) || !(await verifyResearchCsrf(request, identity, env))) return apiError("REQUEST_INTEGRITY_FAILED", 403);
    if (request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase() !== "application/json") {
      return apiError("UNSUPPORTED_MEDIA_TYPE", 415);
    }
  }

  const ownerId = await founderOwnerId(identity);
  const now = new Date().toISOString();
  try {
    if (request.method === "GET" && path === "/bootstrap") {
      await ensureDefaultWatchlist(db, ownerId, now);
      return apiJson({
        ...(await recentDashboard(db, ownerId)),
        csrf_token: await issueResearchCsrf(identity, env),
        session_expires_at: identity.expiresAt ? new Date(identity.expiresAt * 1000).toISOString() : null,
        generated_at: now,
      });
    }
    if (request.method === "GET" && path === "/markets") return apiJson({ instruments: await listResearchInstruments(db), generated_at: now });
    if (request.method === "GET" && path === "/macro") return apiJson({ macro: await listMacro(db), generated_at: now });
    if (request.method === "GET" && path === "/health") return apiJson({ providers: await listProviderHealth(db), generated_at: now });
    if (request.method === "GET" && path === "/brief") {
      return apiJson({
        brief: await getMarketIntelligenceBrief(db, now),
      });
    }
    if (request.method === "GET" && path === "/watchlists") return apiJson({ watchlists: await listWatchlists(db, ownerId) });
    if (request.method === "POST" && path === "/watchlists") {
      const body = await exactJsonBody(request);
      const input = exactWatchlistInput(body, false);
      return apiJson({ watchlist: await createWatchlist(db, ownerId, input.name, input.instrumentIds, now) }, 201);
    }
    const watchlistMatch = path.match(/^\/watchlists\/([0-9a-f-]{36}|default-[0-9a-f]{64})$/u);
    if (request.method === "PUT" && watchlistMatch) {
      const body = await exactJsonBody(request);
      const input = exactWatchlistInput(body, true);
      const updated = await replaceWatchlist(db, ownerId, watchlistMatch[1], input.name, input.revision, input.instrumentIds, now);
      return updated ? apiJson({ watchlist: updated }) : apiError("REVISION_CONFLICT", 409);
    }
    const dossierMatch = path.match(/^\/instruments\/([A-Z0-9_]{3,80})$/u);
    if (request.method === "GET" && dossierMatch) {
      const dossier = await getInstrumentDossier(db, dossierMatch[1]);
      return dossier ? apiJson(dossier) : apiError("NOT_FOUND", 404);
    }
    if (request.method === "POST" && path === "/compare") {
      const body = await exactJsonBody(request);
      const ids = exactInstrumentIds(body.instrument_ids, 2, 4);
      const series = Object.fromEntries(await Promise.all(ids.map(async (id) => [id, await getPriceBars(db, id)])));
      return apiJson({ comparison: compareSeries(series), instrument_ids: ids, generated_at: now });
    }
    if (request.method === "GET" && path === "/records") {
      const type = url.searchParams.get("type")?.toUpperCase();
      if (type && !RECORD_TYPES.has(type)) return apiError("INVALID_RECORD_TYPE", 400);
      return apiJson({ records: await listRecords(db, ownerId, type || undefined, url.searchParams.get("archived") === "1") });
    }
    if (request.method === "POST" && path === "/records") {
      const input = exactRecordInput(await exactJsonBody(request));
      return apiJson({ record: await createRecord(db, ownerId, input, now) }, 201);
    }
    const revisionsMatch = path.match(/^\/records\/([0-9a-f-]{36})\/revisions$/u);
    if (request.method === "GET" && revisionsMatch) return apiJson({ revisions: await listRecordRevisions(db, ownerId, revisionsMatch[1]) });
    const recordMatch = path.match(/^\/records\/([0-9a-f-]{36})$/u);
    if (request.method === "PUT" && recordMatch) {
      const body = await exactJsonBody(request);
      const revision = exactRevision(body.revision);
      const input = exactRecordInput(body);
      const updated = await updateRecord(db, ownerId, recordMatch[1], revision, input, now);
      return updated ? apiJson({ record: updated }) : apiError("REVISION_CONFLICT", 409);
    }
    if (request.method === "DELETE" && recordMatch) {
      const body = await exactJsonBody(request);
      const revision = exactRevision(body.revision);
      const records = await listRecords(db, ownerId, undefined, true);
      const current = records.find((record) => record.record_id === recordMatch[1]);
      if (!current || current.revision !== revision) return apiError("REVISION_CONFLICT", 409);
      const updated = await updateRecord(db, ownerId, current.record_id, revision, recordToInput({ ...current, status: "ARCHIVED" }), now);
      return updated ? apiJson({ record: updated }) : apiError("REVISION_CONFLICT", 409);
    }
    if (request.method === "GET" && path === "/export") return exportResearch(db, ownerId, url.searchParams.get("format") ?? "json", now);
    return apiError("NOT_FOUND", 404);
  } catch (error) {
    const requestId = crypto.randomUUID();
    console.error(JSON.stringify({
      event: "research_api_failure",
      request_id: requestId,
      method: request.method,
      path,
      error_code: safeErrorCode(error),
      boundary: RESEARCH_BOUNDARY,
      authority_effect: RESEARCH_AUTHORITY,
    }));
    const code = error instanceof ResearchInputError ? error.message : "SERVICE_UNAVAILABLE";
    return apiError(code, error instanceof ResearchInputError ? error.status : 503, requestId);
  }
}

async function exportResearch(db: D1DatabaseLike, ownerId: string, format: string, now: string): Promise<Response> {
  const records = await listRecords(db, ownerId, undefined, true);
  const watchlists = await listWatchlists(db, ownerId);
  if (format === "json") return apiJson({ records, watchlists, exported_at: now, boundary: RESEARCH_BOUNDARY, authority_effect: RESEARCH_AUTHORITY });
  if (format === "csv") {
    const header = "record_id,record_type,title,status,confidence,instrument_id,updated_at";
    const rows = records.map((record) => [
      record.record_id, record.record_type, record.title, record.status,
      record.confidence ?? "", record.instrument_id ?? "", record.updated_at,
    ].map(csvCell).join(","));
    return new Response([header, ...rows].join("\n"), {
      headers: { ...API_HEADERS, "content-type": "text/csv; charset=utf-8", "content-disposition": 'attachment; filename="deltagrid-research.csv"' },
    });
  }
  if (format === "markdown") {
    const body = [`# DeltaGrid Research Export`, "", `Exported: ${now}`, `Boundary: ${RESEARCH_BOUNDARY}`, ""];
    for (const record of records) body.push(`## ${record.title}`, "", `Type: ${record.record_type} · Status: ${record.status} · Revision: ${record.revision}`, "", record.body, "");
    return new Response(body.join("\n"), {
      headers: { ...API_HEADERS, "content-type": "text/markdown; charset=utf-8", "content-disposition": 'attachment; filename="deltagrid-research.md"' },
    });
  }
  throw new ResearchInputError("INVALID_EXPORT_FORMAT", 400);
}

async function exactJsonBody(request: Request): Promise<Record<string, unknown>> {
  const declared = Number(request.headers.get("content-length") ?? 0);
  if (declared > 65_536) throw new ResearchInputError("PAYLOAD_TOO_LARGE", 413);
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > 65_536) throw new ResearchInputError("PAYLOAD_TOO_LARGE", 413);
  try {
    const value: unknown = JSON.parse(text || "{}");
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("object required");
    return value as Record<string, unknown>;
  } catch {
    throw new ResearchInputError("INVALID_JSON", 400);
  }
}

function exactRecordInput(body: Record<string, unknown>): ResearchRecordInput {
  const allowed = new Set([
    "record_type", "instrument_id", "title", "body", "status", "confidence", "tags",
    "source_url", "source_published_at", "source_accessed_at", "due_at", "revision",
  ]);
  if (Object.keys(body).some((key) => !allowed.has(key))) throw new ResearchInputError("INVALID_RECORD_SHAPE", 400);
  const type = exactString(body.record_type, 3, 16).toUpperCase();
  const status = exactString(body.status, 3, 16).toUpperCase();
  if (!RECORD_TYPES.has(type) || !RECORD_STATUSES.has(status)) throw new ResearchInputError("INVALID_RECORD_ENUM", 400);
  const tags = Array.isArray(body.tags) ? body.tags : [];
  if (tags.length > 12 || tags.some((tag) => typeof tag !== "string" || tag.trim().length < 1 || tag.trim().length > 32)) throw new ResearchInputError("INVALID_RECORD_TAGS", 400);
  const confidence = body.confidence === null || body.confidence === undefined ? null : Number(body.confidence);
  if (confidence !== null && (!Number.isInteger(confidence) || confidence < 0 || confidence > 100)) throw new ResearchInputError("INVALID_RECORD_CONFIDENCE", 400);
  const sourceUrl = exactNullableString(body.source_url, 2048);
  if (sourceUrl) {
    try {
      const parsed = new URL(sourceUrl);
      if (parsed.protocol !== "https:" && parsed.protocol !== "http:") throw new Error("scheme");
    } catch {
      throw new ResearchInputError("INVALID_SOURCE_URL", 400);
    }
  }
  return {
    record_type: type as ResearchRecordInput["record_type"],
    instrument_id: exactNullablePattern(body.instrument_id, /^[A-Z0-9_]{3,80}$/u),
    title: exactString(body.title, 1, 180),
    body: exactString(body.body ?? "", 0, 32_768),
    status: status as ResearchRecordInput["status"],
    confidence,
    tags_json: JSON.stringify(tags.map((tag) => String(tag).trim())),
    source_url: sourceUrl,
    source_published_at: exactNullableIso(body.source_published_at),
    source_accessed_at: exactNullableIso(body.source_accessed_at),
    due_at: exactNullableIso(body.due_at),
  };
}

function exactWatchlistInput(body: Record<string, unknown>, revisionRequired: boolean): { name: string; instrumentIds: string[]; revision: number } {
  const allowed = new Set(["name", "instrument_ids", "revision"]);
  if (Object.keys(body).some((key) => !allowed.has(key))) throw new ResearchInputError("INVALID_WATCHLIST_SHAPE", 400);
  return {
    name: exactString(body.name, 1, 80),
    instrumentIds: exactInstrumentIds(body.instrument_ids, 0, 40),
    revision: revisionRequired ? exactRevision(body.revision) : 1,
  };
}

function exactInstrumentIds(value: unknown, minimum: number, maximum: number): string[] {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) throw new ResearchInputError("INVALID_INSTRUMENT_SELECTION", 400);
  const ids = value.map((entry) => exactString(entry, 3, 80));
  if (ids.some((id) => !/^[A-Z0-9_]+$/u.test(id)) || new Set(ids).size !== ids.length) throw new ResearchInputError("INVALID_INSTRUMENT_SELECTION", 400);
  return ids;
}

function exactRevision(value: unknown): number {
  const revision = Number(value);
  if (!Number.isInteger(revision) || revision < 1 || revision > 1_000_000) throw new ResearchInputError("INVALID_REVISION", 400);
  return revision;
}

function exactString(value: unknown, minimum: number, maximum: number): string {
  if (typeof value !== "string") throw new ResearchInputError("INVALID_STRING", 400);
  const normalized = value.trim();
  if (normalized.length < minimum || normalized.length > maximum) throw new ResearchInputError("INVALID_STRING", 400);
  return normalized;
}

function exactNullableString(value: unknown, maximum: number): string | null {
  if (value === null || value === undefined || value === "") return null;
  return exactString(value, 1, maximum);
}

function exactNullablePattern(value: unknown, pattern: RegExp): string | null {
  const result = exactNullableString(value, 80);
  if (result && !pattern.test(result)) throw new ResearchInputError("INVALID_IDENTIFIER", 400);
  return result;
}

function exactNullableIso(value: unknown): string | null {
  const result = exactNullableString(value, 40);
  if (result && (Number.isNaN(Date.parse(result)) || !/^\d{4}-\d{2}-\d{2}T/u.test(result))) throw new ResearchInputError("INVALID_TIMESTAMP", 400);
  return result;
}

function recordToInput(record: ResearchRecord): ResearchRecordInput {
  return {
    record_type: record.record_type,
    instrument_id: record.instrument_id,
    title: record.title,
    body: record.body,
    status: record.status,
    confidence: record.confidence,
    tags_json: record.tags_json,
    source_url: record.source_url,
    source_published_at: record.source_published_at,
    source_accessed_at: record.source_accessed_at,
    due_at: record.due_at,
  };
}

function csvCell(value: unknown): string {
  return `"${String(value).replaceAll('"', '""')}"`;
}

function apiJson(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: API_HEADERS });
}

function apiError(code: string, status: number, requestId?: string): Response {
  return apiJson({ error: code, ...(requestId ? { request_id: requestId } : {}) }, status);
}

function safeErrorCode(error: unknown): string {
  return error instanceof Error && /^[A-Z0-9_]{3,96}$/u.test(error.message) ? error.message : "UNCLASSIFIED_FAILURE";
}

class ResearchInputError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
