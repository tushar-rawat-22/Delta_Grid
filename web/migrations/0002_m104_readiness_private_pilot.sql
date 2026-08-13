PRAGMA foreign_keys = ON;

ALTER TABLE provider_registry ADD COLUMN rights_classification TEXT NOT NULL DEFAULT 'UNKNOWN_RESTRICTIVE';
ALTER TABLE provider_registry ADD COLUMN quota_policy TEXT NOT NULL DEFAULT 'ONE_REQUEST_PER_PROVIDER_PER_UTC_DAY';
ALTER TABLE provider_registry ADD COLUMN terms_review_status TEXT NOT NULL DEFAULT 'UNKNOWN_RESTRICTIVE';
ALTER TABLE provider_registry ADD COLUMN retention_policy TEXT NOT NULL DEFAULT 'PRIVATE_LOCAL_RAW_METADATA_ONLY_REMOTE';
ALTER TABLE provider_registry ADD COLUMN research_eligibility TEXT NOT NULL DEFAULT 'NOT_ELIGIBLE';
ALTER TABLE provider_registry ADD COLUMN last_terms_review_at TEXT;
ALTER TABLE provider_registry ADD COLUMN collection_cadence_seconds INTEGER NOT NULL DEFAULT 86400;

UPDATE provider_registry
SET rights_classification = 'PUBLIC_SOURCE_PRIVATE_METADATA_ONLY',
    quota_policy = 'ONE_REQUEST_PER_PROVIDER_PER_UTC_DAY',
    terms_review_status = 'REVIEWED_PUBLIC_API_PRIVATE_RESEARCH',
    retention_policy = 'PRIVATE_LOCAL_RAW_METADATA_ONLY_REMOTE',
    research_eligibility = 'PRIVATE_RESEARCH_ONLY',
    last_terms_review_at = '2026-08-13T00:00:00.000Z',
    collection_cadence_seconds = 86400
WHERE provider_id IN ('SEC_EDGAR_PRIVATE_PILOT', 'US_TREASURY_FISCALDATA_PRIVATE_PILOT');

ALTER TABLE temporal_evidence_envelopes ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE temporal_evidence_envelopes ADD COLUMN content_length INTEGER NOT NULL DEFAULT 1;
ALTER TABLE temporal_evidence_envelopes ADD COLUMN provider_record_date TEXT NOT NULL DEFAULT '1970-01-01';
ALTER TABLE temporal_evidence_envelopes ADD COLUMN local_receipt_sha256 TEXT NOT NULL DEFAULT '0000000000000000000000000000000000000000000000000000000000000000';
ALTER TABLE temporal_evidence_envelopes ADD COLUMN received_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00.000Z';
ALTER TABLE temporal_evidence_envelopes ADD COLUMN research_eligible INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX temporal_evidence_provider_payload_replay
  ON temporal_evidence_envelopes(provider_id, payload_sha256, provider_record_date);

CREATE TABLE provider_health_receipts (
  receipt_id TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES provider_registry(provider_id),
  recorded_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('OPERATIONAL', 'DEGRADED', 'FAILED')),
  latest_envelope_id TEXT,
  payload_sha256 TEXT CHECK (payload_sha256 IS NULL OR length(payload_sha256) = 64),
  local_receipt_sha256 TEXT NOT NULL CHECK (length(local_receipt_sha256) = 64),
  detail_code TEXT NOT NULL,
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  FOREIGN KEY (latest_envelope_id) REFERENCES temporal_evidence_envelopes(envelope_id)
);

CREATE INDEX provider_health_latest
  ON provider_health_receipts(provider_id, recorded_at DESC);

CREATE TRIGGER temporal_evidence_append_only_update
BEFORE UPDATE ON temporal_evidence_envelopes BEGIN SELECT RAISE(ABORT, 'TEMPORAL_EVIDENCE_APPEND_ONLY'); END;
CREATE TRIGGER temporal_evidence_append_only_delete
BEFORE DELETE ON temporal_evidence_envelopes BEGIN SELECT RAISE(ABORT, 'TEMPORAL_EVIDENCE_APPEND_ONLY'); END;
CREATE TRIGGER provider_health_append_only_update
BEFORE UPDATE ON provider_health_receipts BEGIN SELECT RAISE(ABORT, 'PROVIDER_HEALTH_APPEND_ONLY'); END;
CREATE TRIGGER provider_health_append_only_delete
BEFORE DELETE ON provider_health_receipts BEGIN SELECT RAISE(ABORT, 'PROVIDER_HEALTH_APPEND_ONLY'); END;
