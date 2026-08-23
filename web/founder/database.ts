import type { ActionId, CommandRecord, CommandStatus } from "./contracts.ts";

export type D1ResultLike<T = Record<string, unknown>> = {
  success: boolean;
  results?: T[];
  meta?: { changes?: number };
};

export type D1StatementLike = {
  bind(...values: unknown[]): D1StatementLike;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  run<T = Record<string, unknown>>(): Promise<D1ResultLike<T>>;
  all<T = Record<string, unknown>>(): Promise<D1ResultLike<T>>;
};

export type D1DatabaseLike = {
  prepare(query: string): D1StatementLike;
  batch<T = Record<string, unknown>>(statements: D1StatementLike[]): Promise<D1ResultLike<T>[]>;
};

export type CommandInsert = Omit<
  CommandRecord,
  "status" | "claimed_at" | "claimed_by" | "executing_at" | "completed_at" | "terminal_code"
>;

export type ReceiptInput = {
  commandId: string;
  agentId: string;
  status: Extract<CommandStatus, "SUCCEEDED" | "FAILED" | "REJECTED">;
  terminalCode: string;
  startedAt: string;
  completedAt: string;
  durationMs: number;
  outputSha256: string;
  localReceiptSha256: string;
};

export type EvidenceEnvelopeInput = {
  envelopeId: string;
  providerId: string;
  instrumentId: string;
  observedAt: string;
  availableAt: string;
  payloadSha256: string;
  contentLength: number;
  providerRecordDate: string;
  localReceiptSha256: string;
  receivedAt: string;
};

export type ProviderHealthInput = {
  receiptId: string;
  providerId: string;
  recordedAt: string;
  status: "OPERATIONAL" | "DEGRADED" | "FAILED";
  latestEnvelopeId: string | null;
  payloadSha256: string | null;
  localReceiptSha256: string;
  detailCode: string;
};

type SecurityActorKind = "FOUNDER" | "AGENT" | "SYSTEM";
type SecurityOutcome = "ALLOW" | "DENY" | "ERROR";

function commandInsertStatement(db: D1DatabaseLike, command: CommandInsert): D1StatementLike {
  return db.prepare(
    `INSERT INTO founder_command_requests (
      command_id, schema_version, requested_action_id, founder_user_id,
      requested_at, expires_at, one_use_nonce, expected_core_commit,
      expected_authority_state, parameter_json, parameter_hash,
      canonical_request_hash, integrity_proof, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'REQUESTED')`,
  ).bind(
    command.command_id,
    command.schema_version,
    command.requested_action_id,
    command.founder_user_id,
    command.requested_at,
    command.expires_at,
    command.one_use_nonce,
    command.expected_core_commit,
    command.expected_authority_state,
    command.parameter_json,
    command.parameter_hash,
    command.canonical_request_hash,
    command.integrity_proof,
  );
}

function securityEventStatement(
  db: D1DatabaseLike,
  eventType: string,
  actorKind: SecurityActorKind,
  outcome: SecurityOutcome,
  reasonCode: string,
): D1StatementLike {
  return db.prepare(
    `INSERT INTO founder_security_events
      (event_id, occurred_at, event_type, actor_kind, outcome, reason_code)
      VALUES (?, ?, ?, ?, ?, ?)`,
  ).bind(crypto.randomUUID(), new Date().toISOString(), eventType, actorKind, outcome, reasonCode);
}

export async function insertCommand(db: D1DatabaseLike, command: CommandInsert): Promise<void> {
  const result = await commandInsertStatement(db, command).run();
  if (!result.success || !changedExactlyOne(result)) throw new Error("COMMAND_INSERT_FAILED");
}

export async function insertCommandWithSecurityEvent(
  db: D1DatabaseLike,
  command: CommandInsert,
): Promise<void> {
  const results = await db.batch([
    commandInsertStatement(db, command),
    securityEventStatement(db, "COMMAND_CREATE", "FOUNDER", "ALLOW", "FIXED_ACTION_ACCEPTED"),
  ]);
  if (results.length !== 2 || results.some((result) => !result.success || !changedExactlyOne(result))) {
    throw new Error("COMMAND_AUDIT_BATCH_FAILED");
  }
}

export async function listRecentCommands(db: D1DatabaseLike, limit = 20): Promise<CommandRecord[]> {
  const bounded = Math.max(1, Math.min(limit, 50));
  const result = await db.prepare(
    `SELECT command_id, schema_version, requested_action_id, founder_user_id,
      requested_at, expires_at, one_use_nonce, expected_core_commit,
      expected_authority_state, parameter_json, parameter_hash,
      canonical_request_hash, integrity_proof, status, claimed_at, claimed_by,
      executing_at, completed_at, terminal_code
    FROM founder_command_requests ORDER BY requested_at DESC LIMIT ?`,
  ).bind(bounded).all<CommandRecord>();
  if (!result.success) throw new Error("COMMAND_LIST_FAILED");
  return result.results ?? [];
}

export async function expireStaleCommands(db: D1DatabaseLike, now: string): Promise<void> {
  const result = await db.prepare(
    `UPDATE founder_command_requests
      SET status = 'EXPIRED', completed_at = ?, terminal_code = 'COMMAND_TTL_EXPIRED'
      WHERE status IN ('REQUESTED', 'CLAIMED') AND expires_at <= ?`,
  ).bind(now, now).run();
  if (!result.success) throw new Error("COMMAND_EXPIRY_FAILED");
}

export async function registerAgentNonce(
  db: D1DatabaseLike,
  agentId: string,
  nonce: string,
  observedAt: string,
): Promise<boolean> {
  try {
    const result = await db.prepare(
      "INSERT INTO founder_agent_nonces (agent_id, nonce, observed_at) VALUES (?, ?, ?)",
    ).bind(agentId, nonce, observedAt).run();
    return result.success && result.meta?.changes === 1;
  } catch {
    return false;
  }
}

export async function claimCommand(
  db: D1DatabaseLike,
  agentId: string,
  coreCommit: string,
  authorityState: string,
  now: string,
): Promise<CommandRecord | null> {
  const candidate = await db.prepare(
    `SELECT command_id FROM founder_command_requests
      WHERE status = 'REQUESTED' AND expires_at > ?
        AND expected_core_commit = ? AND expected_authority_state = ?
      ORDER BY requested_at ASC LIMIT 1`,
  ).bind(now, coreCommit, authorityState).first<{ command_id: string }>();
  if (!candidate) return null;

  const result = await db.prepare(
    `UPDATE founder_command_requests
      SET status = 'CLAIMED', claimed_at = ?, claimed_by = ?
      WHERE command_id = ? AND status = 'REQUESTED' AND expires_at > ?
      RETURNING *`,
  ).bind(now, agentId, candidate.command_id, now).run<CommandRecord>();
  return result.success ? (result.results?.[0] ?? null) : null;
}

export async function startCommand(
  db: D1DatabaseLike,
  commandId: string,
  agentId: string,
  now: string,
): Promise<boolean> {
  const result = await db.prepare(
    `UPDATE founder_command_requests SET status = 'EXECUTING', executing_at = ?
      WHERE command_id = ? AND status = 'CLAIMED' AND claimed_by = ? AND expires_at > ?
      RETURNING command_id`,
  ).bind(now, commandId, agentId, now).run<{ command_id: string }>();
  return result.success && changedExactlyOne(result);
}

export async function completeCommand(db: D1DatabaseLike, receipt: ReceiptInput): Promise<boolean> {
  const receiptId = crypto.randomUUID();
  const statements = [
    db.prepare(
      `UPDATE founder_command_requests SET status = ?, completed_at = ?, terminal_code = ?
        WHERE command_id = ? AND status = 'EXECUTING' AND claimed_by = ?
        RETURNING command_id`,
    ).bind(receipt.status, receipt.completedAt, receipt.terminalCode, receipt.commandId, receipt.agentId),
    db.prepare(
      `INSERT INTO founder_command_receipts (
        receipt_id, command_id, agent_id, terminal_status, terminal_code,
        started_at, completed_at, duration_ms, output_sha256, local_receipt_sha256
      ) SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        WHERE EXISTS (
          SELECT 1 FROM founder_command_requests
          WHERE command_id = ? AND status = ? AND claimed_by = ?
        ) RETURNING receipt_id`,
    ).bind(
      receiptId,
      receipt.commandId,
      receipt.agentId,
      receipt.status,
      receipt.terminalCode,
      receipt.startedAt,
      receipt.completedAt,
      receipt.durationMs,
      receipt.outputSha256,
      receipt.localReceiptSha256,
      receipt.commandId,
      receipt.status,
      receipt.agentId,
    ),
  ];
  const results = await db.batch(statements);
  return results.every((result) => result.success) && results.every(changedExactlyOne);
}

function changedExactlyOne(result: D1ResultLike): boolean {
  return result.results?.length === 1 || result.meta?.changes === 1;
}

export async function systemCounts(db: D1DatabaseLike): Promise<Record<string, number>> {
  const row = await db.prepare(
    `SELECT
      (SELECT COUNT(*) FROM founder_command_requests) AS commands,
      (SELECT COUNT(*) FROM founder_command_requests WHERE status = 'REQUESTED') AS requested,
      (SELECT COUNT(*) FROM founder_command_requests WHERE status = 'EXECUTING') AS executing,
      (SELECT COUNT(*) FROM founder_command_receipts) AS receipts,
      (SELECT COUNT(*) FROM provider_registry) AS providers,
      (SELECT COUNT(*) FROM instrument_master) AS instruments,
      (SELECT COUNT(*) FROM temporal_evidence_envelopes) AS evidence_envelopes,
      (SELECT COUNT(*) FROM provider_health_receipts WHERE status = 'OPERATIONAL') AS operational_receipts`,
  ).first<Record<string, number>>();
  if (!row) throw new Error("SYSTEM_COUNTS_FAILED");
  return row;
}

export async function insertEvidenceEnvelope(
  db: D1DatabaseLike,
  envelope: EvidenceEnvelopeInput,
): Promise<boolean> {
  try {
    const result = await db.prepare(
      `INSERT INTO temporal_evidence_envelopes (
        envelope_id, provider_id, instrument_id, observed_at, available_at,
        payload_sha256, private_only, authority_effect, schema_version,
        content_length, provider_record_date, local_receipt_sha256, received_at,
        research_eligible
      ) VALUES (?, ?, ?, ?, ?, ?, 1, 'NONE', 1, ?, ?, ?, ?, 1)
      RETURNING envelope_id`,
    ).bind(
      envelope.envelopeId,
      envelope.providerId,
      envelope.instrumentId,
      envelope.observedAt,
      envelope.availableAt,
      envelope.payloadSha256,
      envelope.contentLength,
      envelope.providerRecordDate,
      envelope.localReceiptSha256,
      envelope.receivedAt,
    ).run<{ envelope_id: string }>();
    return result.success && changedExactlyOne(result);
  } catch {
    return false;
  }
}

export async function insertProviderHealth(
  db: D1DatabaseLike,
  receipt: ProviderHealthInput,
): Promise<boolean> {
  try {
    const result = await db.prepare(
      `INSERT INTO provider_health_receipts (
        receipt_id, provider_id, recorded_at, status, latest_envelope_id,
        payload_sha256, local_receipt_sha256, detail_code, authority_effect
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NONE') RETURNING receipt_id`,
    ).bind(
      receipt.receiptId,
      receipt.providerId,
      receipt.recordedAt,
      receipt.status,
      receipt.latestEnvelopeId,
      receipt.payloadSha256,
      receipt.localReceiptSha256,
      receipt.detailCode,
    ).run<{ receipt_id: string }>();
    return result.success && changedExactlyOne(result);
  } catch {
    return false;
  }
}

export async function insertSecurityEvent(
  db: D1DatabaseLike,
  eventType: string,
  actorKind: SecurityActorKind,
  outcome: SecurityOutcome,
  reasonCode: string,
): Promise<void> {
  const result = await securityEventStatement(db, eventType, actorKind, outcome, reasonCode).run();
  if (!result.success || !changedExactlyOne(result)) throw new Error("SECURITY_EVENT_INSERT_FAILED");
}

export function assertActionId(value: string): ActionId {
  return value as ActionId;
}
