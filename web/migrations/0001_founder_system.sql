PRAGMA foreign_keys = ON;

CREATE TABLE founder_command_requests (
  command_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL CHECK (schema_version = 1),
  requested_action_id TEXT NOT NULL CHECK (requested_action_id IN (
    'VERIFY_CORE_STATUS', 'VERIFY_M100_JOURNAL', 'CAPTURE_M100_ONCE',
    'EXPORT_M100_BACKUP', 'VERIFY_M100_BACKUP', 'REFRESH_PUBLIC_PROJECTION',
    'VERIFY_PUBLIC_PROJECTION', 'RUN_APPROVED_TEST_PROFILE',
    'SHOW_CONTRACT_IDENTITIES', 'SHOW_WORKTREE_STATUS'
  )),
  founder_user_id TEXT NOT NULL,
  requested_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  one_use_nonce TEXT NOT NULL UNIQUE,
  expected_core_commit TEXT NOT NULL CHECK (length(expected_core_commit) = 40),
  expected_authority_state TEXT NOT NULL CHECK (expected_authority_state = 'NONE'),
  parameter_json TEXT NOT NULL CHECK (parameter_json = '{}'),
  parameter_hash TEXT NOT NULL CHECK (length(parameter_hash) = 64),
  canonical_request_hash TEXT NOT NULL UNIQUE CHECK (length(canonical_request_hash) = 64),
  integrity_proof TEXT NOT NULL CHECK (length(integrity_proof) = 64),
  status TEXT NOT NULL CHECK (status IN (
    'REQUESTED', 'CLAIMED', 'EXECUTING', 'SUCCEEDED', 'FAILED', 'REJECTED', 'EXPIRED'
  )),
  claimed_at TEXT,
  claimed_by TEXT,
  executing_at TEXT,
  completed_at TEXT,
  terminal_code TEXT
);

CREATE INDEX founder_commands_status_time
  ON founder_command_requests(status, requested_at);

CREATE TABLE founder_command_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  command_id TEXT NOT NULL REFERENCES founder_command_requests(command_id),
  occurred_at TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  reason_code TEXT NOT NULL
);

CREATE TABLE founder_command_receipts (
  receipt_id TEXT PRIMARY KEY,
  command_id TEXT NOT NULL UNIQUE REFERENCES founder_command_requests(command_id),
  agent_id TEXT NOT NULL,
  terminal_status TEXT NOT NULL CHECK (terminal_status IN ('SUCCEEDED', 'FAILED', 'REJECTED')),
  terminal_code TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0 AND duration_ms <= 86400000),
  output_sha256 TEXT NOT NULL CHECK (length(output_sha256) = 64),
  local_receipt_sha256 TEXT NOT NULL CHECK (length(local_receipt_sha256) = 64)
);

CREATE TABLE founder_agent_nonces (
  agent_id TEXT NOT NULL,
  nonce TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  PRIMARY KEY (agent_id, nonce)
);

CREATE TABLE founder_security_events (
  event_id TEXT PRIMARY KEY,
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor_kind TEXT NOT NULL CHECK (actor_kind IN ('FOUNDER', 'AGENT', 'SYSTEM')),
  outcome TEXT NOT NULL CHECK (outcome IN ('ALLOW', 'DENY', 'ERROR')),
  reason_code TEXT NOT NULL
);

CREATE TABLE provider_registry (
  provider_id TEXT PRIMARY KEY,
  provider_name TEXT NOT NULL,
  provider_class TEXT NOT NULL,
  access_mode TEXT NOT NULL,
  display_rights TEXT NOT NULL,
  production_collection_enabled INTEGER NOT NULL CHECK (production_collection_enabled IN (0, 1)),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  reviewed_at TEXT NOT NULL
);

CREATE TABLE instrument_master (
  instrument_id TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES provider_registry(provider_id),
  asset_class TEXT NOT NULL,
  canonical_symbol TEXT NOT NULL,
  provider_symbol TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  status TEXT NOT NULL CHECK (status IN ('PRIVATE_PILOT', 'ACTIVE', 'RETIRED')),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  UNIQUE(provider_id, provider_symbol, valid_from)
);

CREATE TABLE temporal_evidence_envelopes (
  envelope_id TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES provider_registry(provider_id),
  instrument_id TEXT REFERENCES instrument_master(instrument_id),
  observed_at TEXT NOT NULL,
  available_at TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
  private_only INTEGER NOT NULL CHECK (private_only = 1),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE')
);

CREATE TRIGGER founder_command_insert_event
AFTER INSERT ON founder_command_requests
BEGIN
  INSERT INTO founder_command_events(command_id, occurred_at, from_status, to_status, reason_code)
  VALUES (NEW.command_id, NEW.requested_at, NULL, NEW.status, 'FOUNDER_REQUEST_ACCEPTED');
END;

CREATE TRIGGER founder_command_immutable_fields
BEFORE UPDATE ON founder_command_requests
WHEN OLD.command_id != NEW.command_id
  OR OLD.schema_version != NEW.schema_version
  OR OLD.requested_action_id != NEW.requested_action_id
  OR OLD.founder_user_id != NEW.founder_user_id
  OR OLD.requested_at != NEW.requested_at
  OR OLD.expires_at != NEW.expires_at
  OR OLD.one_use_nonce != NEW.one_use_nonce
  OR OLD.expected_core_commit != NEW.expected_core_commit
  OR OLD.expected_authority_state != NEW.expected_authority_state
  OR OLD.parameter_json != NEW.parameter_json
  OR OLD.parameter_hash != NEW.parameter_hash
  OR OLD.canonical_request_hash != NEW.canonical_request_hash
  OR OLD.integrity_proof != NEW.integrity_proof
BEGIN
  SELECT RAISE(ABORT, 'COMMAND_IMMUTABLE_FIELD_MUTATION');
END;

CREATE TRIGGER founder_command_transition_guard
BEFORE UPDATE OF status ON founder_command_requests
WHEN NOT (
  (OLD.status = 'REQUESTED' AND NEW.status IN ('CLAIMED', 'REJECTED', 'EXPIRED')) OR
  (OLD.status = 'CLAIMED' AND NEW.status IN ('EXECUTING', 'REJECTED', 'EXPIRED')) OR
  (OLD.status = 'EXECUTING' AND NEW.status IN ('SUCCEEDED', 'FAILED', 'REJECTED'))
)
BEGIN
  SELECT RAISE(ABORT, 'COMMAND_STATE_TRANSITION_INVALID');
END;

CREATE TRIGGER founder_command_update_event
AFTER UPDATE OF status ON founder_command_requests
BEGIN
  INSERT INTO founder_command_events(command_id, occurred_at, from_status, to_status, reason_code)
  VALUES (
    NEW.command_id,
    COALESCE(NEW.completed_at, NEW.executing_at, NEW.claimed_at, CURRENT_TIMESTAMP),
    OLD.status,
    NEW.status,
    COALESCE(NEW.terminal_code, 'COMMAND_STATE_ADVANCED')
  );
END;

CREATE TRIGGER founder_command_events_append_only_update
BEFORE UPDATE ON founder_command_events BEGIN SELECT RAISE(ABORT, 'COMMAND_EVENTS_APPEND_ONLY'); END;
CREATE TRIGGER founder_command_events_append_only_delete
BEFORE DELETE ON founder_command_events BEGIN SELECT RAISE(ABORT, 'COMMAND_EVENTS_APPEND_ONLY'); END;
CREATE TRIGGER founder_receipts_append_only_update
BEFORE UPDATE ON founder_command_receipts BEGIN SELECT RAISE(ABORT, 'COMMAND_RECEIPTS_APPEND_ONLY'); END;
CREATE TRIGGER founder_receipts_append_only_delete
BEFORE DELETE ON founder_command_receipts BEGIN SELECT RAISE(ABORT, 'COMMAND_RECEIPTS_APPEND_ONLY'); END;
CREATE TRIGGER founder_security_events_append_only_update
BEFORE UPDATE ON founder_security_events BEGIN SELECT RAISE(ABORT, 'SECURITY_EVENTS_APPEND_ONLY'); END;
CREATE TRIGGER founder_security_events_append_only_delete
BEFORE DELETE ON founder_security_events BEGIN SELECT RAISE(ABORT, 'SECURITY_EVENTS_APPEND_ONLY'); END;

INSERT INTO provider_registry VALUES
  ('SEC_EDGAR_PRIVATE_PILOT', 'U.S. SEC EDGAR', 'OFFICIAL_REGULATOR', 'PUBLIC_HTTPS',
   'PRIVATE_METADATA_ONLY', 0, 'NONE', '2026-08-12T00:00:00.000Z'),
  ('US_TREASURY_FISCALDATA_PRIVATE_PILOT', 'U.S. Treasury Fiscal Data', 'OFFICIAL_GOVERNMENT',
   'PUBLIC_HTTPS', 'PRIVATE_METADATA_ONLY', 0, 'NONE', '2026-08-12T00:00:00.000Z');

INSERT INTO instrument_master VALUES
  ('US_EQUITY_AAPL_PRIVATE_PILOT', 'SEC_EDGAR_PRIVATE_PILOT', 'US_EQUITY', 'AAPL', 'AAPL',
   '2026-08-12T00:00:00.000Z', NULL, 'PRIVATE_PILOT', 'NONE'),
  ('US_MACRO_TREASURY_DEBT_PRIVATE_PILOT', 'US_TREASURY_FISCALDATA_PRIVATE_PILOT', 'US_MACRO',
   'TREASURY_TOTAL_PUBLIC_DEBT', 'Debt to the Penny', '2026-08-12T00:00:00.000Z', NULL,
   'PRIVATE_PILOT', 'NONE');
