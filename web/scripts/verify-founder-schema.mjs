import fs from "node:fs";
import { DatabaseSync } from "node:sqlite";

const database = new DatabaseSync(":memory:");
for (const migration of fs.readdirSync("migrations").filter((name) => name.endsWith(".sql")).sort()) {
  database.exec(fs.readFileSync(`migrations/${migration}`, "utf8"));
}

const providers = database.prepare("SELECT COUNT(*) AS count FROM provider_registry").get().count;
const instruments = database.prepare("SELECT COUNT(*) AS count FROM instrument_master").get().count;
if (providers !== 2 || instruments !== 2) throw new Error("FOUNDER_PRIVATE_PILOT_SEED_INVALID");
const eligibility = database.prepare("SELECT COUNT(*) AS count FROM provider_registry WHERE research_eligibility='PRIVATE_RESEARCH_ONLY'").get().count;
if (eligibility !== 2) throw new Error("FOUNDER_PRIVATE_PILOT_RIGHTS_INVALID");

const researchInstruments = database.prepare("SELECT COUNT(*) AS count FROM research_instruments").get().count;
const researchProviderState = database.prepare("SELECT COUNT(*) AS count FROM research_provider_state").get().count;
if (researchInstruments !== 20 || researchProviderState !== 20) throw new Error("RESEARCH_ENGINE_SEED_INVALID");
const researchBoundaries = database.prepare(`SELECT COUNT(*) AS count FROM research_instruments
  WHERE boundary='NON_RAB1_RESEARCH_ONLY' AND authority_effect='NONE'`).get().count;
if (researchBoundaries !== researchInstruments) throw new Error("RESEARCH_ENGINE_BOUNDARY_INVALID");
const researchSchema = database.prepare(`SELECT group_concat(sql, '\n') AS sql FROM sqlite_schema
  WHERE name LIKE 'research_%'`).get().sql;
for (const forbidden of ["governance", "m100", "m101", "m102", "m103", "temporal_evidence_envelopes"]) {
  if (String(researchSchema).toLowerCase().includes(forbidden)) throw new Error(`RESEARCH_ENGINE_PROTECTED_SCHEMA_REFERENCE:${forbidden}`);
}

database.prepare(`INSERT INTO research_records (
  record_id, owner_id, record_type, instrument_id, title, body, status, confidence,
  tags_json, revision, created_at, updated_at, boundary, authority_effect
) VALUES (?, ?, 'THESIS', 'EQUITY_AAPL', 'Fixture thesis', 'Fixture only', 'DRAFT', 50,
  '[]', 1, ?, ?, 'NON_RAB1_RESEARCH_ONLY', 'NONE')`).run(
  "00000000-0000-4000-8000-000000000020", "f".repeat(64),
  "2026-08-13T00:00:00.000Z", "2026-08-13T00:00:00.000Z",
);
const researchRevisionId = database.prepare("SELECT revision_id FROM research_record_revisions WHERE record_id=? AND revision=1")
  .get("00000000-0000-4000-8000-000000000020").revision_id;
database.prepare(`INSERT INTO research_provider_receipts (
  receipt_id, scheduled_bucket, provider_id, instrument_id, attempted_at, completed_at,
  status, response_sha256, response_bytes, record_count, detail_code, boundary, authority_effect
) VALUES (?, ?, 'COINBASE_EXCHANGE', 'CRYPTO_BTC_USD', ?, ?, 'OPERATIONAL', ?, 100, 1,
  'COLLECTION_SUCCEEDED', 'NON_RAB1_RESEARCH_ONLY', 'NONE')`).run(
  "00000000-0000-4000-8000-000000000022", "2026-08-13T00:00:00.000Z",
  "2026-08-13T00:00:00.000Z", "2026-08-13T00:00:01.000Z", "a".repeat(64),
);
for (const query of [
  `UPDATE research_record_revisions SET revision=2 WHERE revision_id='${researchRevisionId}'`,
  `DELETE FROM research_record_revisions WHERE revision_id='${researchRevisionId}'`,
  "UPDATE research_provider_receipts SET detail_code='MUTATED' WHERE receipt_id='00000000-0000-4000-8000-000000000022'",
  "DELETE FROM research_provider_receipts WHERE receipt_id='00000000-0000-4000-8000-000000000022'",
]) {
  let rejected = false;
  try { database.prepare(query).run(); } catch { rejected = true; }
  if (!rejected) throw new Error(`RESEARCH_ENGINE_APPEND_ONLY_FAIL_OPEN:${query}`);
}

const evidence = [
  "00000000-0000-4000-8000-000000000010", "SEC_EDGAR_PRIVATE_PILOT",
  "US_EQUITY_AAPL_PRIVATE_PILOT", "2026-08-13T00:00:00.000Z",
  "2026-08-13T00:00:01.000Z", "d".repeat(64), 1, "NONE", 1, 1024,
  "2026-08-12", "e".repeat(64), "2026-08-13T00:00:02.000Z", 1,
];
database.prepare(`INSERT INTO temporal_evidence_envelopes (
  envelope_id, provider_id, instrument_id, observed_at, available_at, payload_sha256,
  private_only, authority_effect, schema_version, content_length, provider_record_date,
  local_receipt_sha256, received_at, research_eligible
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(...evidence);
let evidenceReplayRejected = false;
try {
  database.prepare(`INSERT INTO temporal_evidence_envelopes (
    envelope_id, provider_id, instrument_id, observed_at, available_at, payload_sha256,
    private_only, authority_effect, schema_version, content_length, provider_record_date,
    local_receipt_sha256, received_at, research_eligible
  ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(
    "00000000-0000-4000-8000-000000000011", ...evidence.slice(1),
  );
} catch {
  evidenceReplayRejected = true;
}
if (!evidenceReplayRejected) throw new Error("FOUNDER_EVIDENCE_REPLAY_ACCEPTED");

const command = [
  "00000000-0000-4000-8000-000000000000", 1, "VERIFY_CORE_STATUS", "f".repeat(64),
  "2026-08-13T00:00:00.000Z", "2026-08-13T00:05:00.000Z", "0".repeat(32),
  "d94441f2f32fd8edc7b416beecd88b2b087d01a9", "NONE", "{}", "a".repeat(64),
  "b".repeat(64), "c".repeat(64), "REQUESTED",
];
database.prepare(`INSERT INTO founder_command_requests (
  command_id, schema_version, requested_action_id, founder_user_id, requested_at, expires_at,
  one_use_nonce, expected_core_commit, expected_authority_state, parameter_json, parameter_hash,
  canonical_request_hash, integrity_proof, status
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`).run(...command);

database.prepare("UPDATE founder_command_requests SET status='CLAIMED', claimed_at=?, claimed_by=? WHERE command_id=?")
  .run("2026-08-13T00:00:10.000Z", "agent", command[0]);
database.prepare("UPDATE founder_command_requests SET status='EXECUTING', executing_at=? WHERE command_id=?")
  .run("2026-08-13T00:00:11.000Z", command[0]);
database.prepare("UPDATE founder_command_requests SET status='SUCCEEDED', completed_at=?, terminal_code=? WHERE command_id=?")
  .run("2026-08-13T00:00:12.000Z", "ACTION_COMPLETED", command[0]);

const events = database.prepare("SELECT COUNT(*) AS count FROM founder_command_events WHERE command_id=?").get(command[0]).count;
if (events !== 4) throw new Error("FOUNDER_COMMAND_EVENT_CHAIN_INVALID");

for (const query of [
  "UPDATE founder_command_requests SET status='REQUESTED' WHERE command_id=?",
  "UPDATE founder_command_requests SET requested_action_id='SHOW_WORKTREE_STATUS' WHERE command_id=?",
  "DELETE FROM founder_command_events WHERE command_id=?",
]) {
  let rejected = false;
  try {
    database.prepare(query).run(command[0]);
  } catch {
    rejected = true;
  }
  if (!rejected) throw new Error(`FOUNDER_SCHEMA_FAIL_OPEN:${query}`);
}

const foreignKeyFailures = database.prepare("PRAGMA foreign_key_check").all();
if (foreignKeyFailures.length !== 0) throw new Error("FOUNDER_SCHEMA_FOREIGN_KEY_FAILURE");

console.log("FOUNDER_D1_SCHEMA=PASS");
console.log("FOUNDER_COMMAND_TRANSITIONS=PASS");
console.log("FOUNDER_APPEND_ONLY_GUARDS=PASS");
console.log("FOUNDER_PRIVATE_MULTI_MARKET_FOUNDATION=PASS");
console.log("FOUNDER_PRIVATE_PILOT_RIGHTS=RESTRICTIVE_METADATA_ONLY");
console.log("FOUNDER_D1_EVIDENCE_REPLAY=REJECTED");
console.log("RESEARCH_ENGINE_SCHEMA=PASS");
console.log("RESEARCH_ENGINE_BOUNDARY=NON_RAB1_RESEARCH_ONLY");
console.log("RESEARCH_ENGINE_APPEND_ONLY_RECEIPTS=PASS");
