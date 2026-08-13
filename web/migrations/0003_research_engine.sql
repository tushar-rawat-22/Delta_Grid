PRAGMA foreign_keys = ON;

CREATE TABLE research_instruments (
  instrument_id TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL CHECK (provider_id IN (
    'COINBASE_EXCHANGE', 'ALPHA_VANTAGE', 'FRED', 'SEC_COMPANYFACTS', 'US_TREASURY_FISCALDATA'
  )),
  symbol TEXT NOT NULL,
  display_name TEXT NOT NULL,
  asset_class TEXT NOT NULL CHECK (asset_class IN ('CRYPTO', 'US_EQUITY', 'US_ETF', 'MACRO', 'FUNDAMENTAL')),
  provider_symbol TEXT NOT NULL,
  cik TEXT,
  cadence_seconds INTEGER NOT NULL CHECK (cadence_seconds BETWEEN 3600 AND 604800),
  rights_classification TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  created_at TEXT NOT NULL,
  UNIQUE(provider_id, provider_symbol)
);

CREATE TABLE research_price_observations (
  instrument_id TEXT NOT NULL REFERENCES research_instruments(instrument_id),
  observed_at TEXT NOT NULL,
  available_at TEXT NOT NULL,
  interval TEXT NOT NULL CHECK (interval IN ('HOUR', 'DAY', 'WEEK')),
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume REAL,
  adjusted INTEGER NOT NULL CHECK (adjusted IN (0, 1)),
  source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  PRIMARY KEY (instrument_id, observed_at, interval)
);

CREATE INDEX research_prices_instrument_time
  ON research_price_observations(instrument_id, interval, observed_at DESC);

CREATE TABLE research_macro_observations (
  instrument_id TEXT NOT NULL REFERENCES research_instruments(instrument_id),
  observed_at TEXT NOT NULL,
  available_at TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  frequency TEXT NOT NULL,
  source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  PRIMARY KEY (instrument_id, observed_at)
);

CREATE TABLE research_fundamental_facts (
  instrument_id TEXT NOT NULL REFERENCES research_instruments(instrument_id),
  metric_key TEXT NOT NULL,
  period_end TEXT NOT NULL,
  filed_at TEXT NOT NULL,
  form TEXT NOT NULL,
  unit TEXT NOT NULL,
  value REAL NOT NULL,
  accession_number TEXT NOT NULL,
  available_at TEXT NOT NULL,
  source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  PRIMARY KEY (instrument_id, metric_key, period_end, accession_number)
);

CREATE INDEX research_fundamentals_instrument_period
  ON research_fundamental_facts(instrument_id, period_end DESC);

CREATE TABLE research_provider_state (
  provider_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL REFERENCES research_instruments(instrument_id),
  status TEXT NOT NULL CHECK (status IN ('PENDING', 'OPERATIONAL', 'DEGRADED', 'FAILED')),
  last_attempt_at TEXT,
  last_success_at TEXT,
  next_due_at TEXT NOT NULL,
  detail_code TEXT NOT NULL,
  quota_state TEXT NOT NULL,
  rights_classification TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  PRIMARY KEY (provider_id, instrument_id)
);

CREATE TABLE research_provider_receipts (
  receipt_id TEXT PRIMARY KEY,
  scheduled_bucket TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL REFERENCES research_instruments(instrument_id),
  attempted_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('OPERATIONAL', 'DEGRADED', 'FAILED', 'SKIPPED')),
  response_sha256 TEXT CHECK (response_sha256 IS NULL OR length(response_sha256) = 64),
  response_bytes INTEGER NOT NULL CHECK (response_bytes >= 0 AND response_bytes <= 4194304),
  record_count INTEGER NOT NULL CHECK (record_count >= 0 AND record_count <= 5000),
  detail_code TEXT NOT NULL,
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  UNIQUE(provider_id, instrument_id, scheduled_bucket)
);

CREATE INDEX research_provider_receipts_latest
  ON research_provider_receipts(provider_id, attempted_at DESC);

CREATE TABLE research_collection_claims (
  provider_id TEXT NOT NULL,
  instrument_id TEXT NOT NULL REFERENCES research_instruments(instrument_id),
  scheduled_bucket TEXT NOT NULL,
  claimed_at TEXT NOT NULL,
  completed_at TEXT,
  outcome TEXT CHECK (outcome IS NULL OR outcome IN ('OPERATIONAL', 'DEGRADED', 'FAILED')),
  PRIMARY KEY (provider_id, instrument_id, scheduled_bucket)
);

CREATE TABLE research_watchlists (
  watchlist_id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  name TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE')
);

CREATE INDEX research_watchlists_owner ON research_watchlists(owner_id, updated_at DESC);

CREATE TABLE research_watchlist_items (
  watchlist_id TEXT NOT NULL REFERENCES research_watchlists(watchlist_id) ON DELETE CASCADE,
  instrument_id TEXT NOT NULL REFERENCES research_instruments(instrument_id),
  position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 1000),
  added_at TEXT NOT NULL,
  PRIMARY KEY (watchlist_id, instrument_id)
);

CREATE TABLE research_records (
  record_id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  record_type TEXT NOT NULL CHECK (record_type IN ('NOTE', 'THESIS', 'EVIDENCE', 'JOURNAL', 'CATALYST', 'RISK', 'TASK')),
  instrument_id TEXT REFERENCES research_instruments(instrument_id),
  title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 180),
  body TEXT NOT NULL CHECK (length(body) <= 32768),
  status TEXT NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'WATCHING', 'DONE', 'ARCHIVED')),
  confidence INTEGER CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 100),
  tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json)),
  source_url TEXT CHECK (source_url IS NULL OR length(source_url) <= 2048),
  source_published_at TEXT,
  source_accessed_at TEXT,
  due_at TEXT,
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE')
);

CREATE INDEX research_records_owner_type
  ON research_records(owner_id, record_type, updated_at DESC);

CREATE TABLE research_record_revisions (
  revision_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES research_records(record_id),
  owner_id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK (revision >= 1),
  snapshot_json TEXT NOT NULL CHECK (json_valid(snapshot_json)),
  recorded_at TEXT NOT NULL,
  boundary TEXT NOT NULL CHECK (boundary = 'NON_RAB1_RESEARCH_ONLY'),
  authority_effect TEXT NOT NULL CHECK (authority_effect = 'NONE'),
  UNIQUE(record_id, revision)
);

CREATE TRIGGER research_record_insert_revision
AFTER INSERT ON research_records
BEGIN
  INSERT INTO research_record_revisions (
    revision_id, record_id, owner_id, revision, snapshot_json, recorded_at, boundary, authority_effect
  ) VALUES (
    lower(hex(randomblob(16))), NEW.record_id, NEW.owner_id, NEW.revision,
    json_object(
      'record_id', NEW.record_id, 'owner_id', NEW.owner_id, 'record_type', NEW.record_type,
      'instrument_id', NEW.instrument_id, 'title', NEW.title, 'body', NEW.body,
      'status', NEW.status, 'confidence', NEW.confidence, 'tags_json', NEW.tags_json,
      'source_url', NEW.source_url, 'source_published_at', NEW.source_published_at,
      'source_accessed_at', NEW.source_accessed_at, 'due_at', NEW.due_at,
      'revision', NEW.revision, 'created_at', NEW.created_at, 'updated_at', NEW.updated_at
    ),
    NEW.updated_at, NEW.boundary, NEW.authority_effect
  );
END;

CREATE TRIGGER research_record_update_guard
BEFORE UPDATE ON research_records
WHEN NEW.record_id != OLD.record_id OR NEW.owner_id != OLD.owner_id
  OR NEW.created_at != OLD.created_at OR NEW.boundary != OLD.boundary
  OR NEW.authority_effect != OLD.authority_effect OR NEW.revision != OLD.revision + 1
BEGIN
  SELECT RAISE(ABORT, 'RESEARCH_RECORD_TRANSITION_INVALID');
END;

CREATE TRIGGER research_record_update_revision
AFTER UPDATE ON research_records
BEGIN
  INSERT INTO research_record_revisions (
    revision_id, record_id, owner_id, revision, snapshot_json, recorded_at, boundary, authority_effect
  ) VALUES (
    lower(hex(randomblob(16))), NEW.record_id, NEW.owner_id, NEW.revision,
    json_object(
      'record_id', NEW.record_id, 'owner_id', NEW.owner_id, 'record_type', NEW.record_type,
      'instrument_id', NEW.instrument_id, 'title', NEW.title, 'body', NEW.body,
      'status', NEW.status, 'confidence', NEW.confidence, 'tags_json', NEW.tags_json,
      'source_url', NEW.source_url, 'source_published_at', NEW.source_published_at,
      'source_accessed_at', NEW.source_accessed_at, 'due_at', NEW.due_at,
      'revision', NEW.revision, 'created_at', NEW.created_at, 'updated_at', NEW.updated_at
    ),
    NEW.updated_at, NEW.boundary, NEW.authority_effect
  );
END;

CREATE TRIGGER research_receipts_append_only_update
BEFORE UPDATE ON research_provider_receipts BEGIN SELECT RAISE(ABORT, 'RESEARCH_RECEIPTS_APPEND_ONLY'); END;
CREATE TRIGGER research_receipts_append_only_delete
BEFORE DELETE ON research_provider_receipts BEGIN SELECT RAISE(ABORT, 'RESEARCH_RECEIPTS_APPEND_ONLY'); END;
CREATE TRIGGER research_revisions_append_only_update
BEFORE UPDATE ON research_record_revisions BEGIN SELECT RAISE(ABORT, 'RESEARCH_REVISIONS_APPEND_ONLY'); END;
CREATE TRIGGER research_revisions_append_only_delete
BEFORE DELETE ON research_record_revisions BEGIN SELECT RAISE(ABORT, 'RESEARCH_REVISIONS_APPEND_ONLY'); END;

INSERT INTO research_instruments VALUES
  ('CRYPTO_BTC_USD', 'COINBASE_EXCHANGE', 'BTC', 'Bitcoin', 'CRYPTO', 'BTC-USD', NULL, 3600, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('CRYPTO_ETH_USD', 'COINBASE_EXCHANGE', 'ETH', 'Ethereum', 'CRYPTO', 'ETH-USD', NULL, 3600, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('CRYPTO_SOL_USD', 'COINBASE_EXCHANGE', 'SOL', 'Solana', 'CRYPTO', 'SOL-USD', NULL, 3600, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('ETF_SPY', 'ALPHA_VANTAGE', 'SPY', 'SPDR S&P 500 ETF Trust', 'US_ETF', 'SPY', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('ETF_QQQ', 'ALPHA_VANTAGE', 'QQQ', 'Invesco QQQ Trust', 'US_ETF', 'QQQ', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('EQUITY_AAPL', 'ALPHA_VANTAGE', 'AAPL', 'Apple Inc.', 'US_EQUITY', 'AAPL', '0000320193', 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('EQUITY_MSFT', 'ALPHA_VANTAGE', 'MSFT', 'Microsoft Corporation', 'US_EQUITY', 'MSFT', '0000789019', 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('EQUITY_NVDA', 'ALPHA_VANTAGE', 'NVDA', 'NVIDIA Corporation', 'US_EQUITY', 'NVDA', '0001045810', 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('FUNDAMENTAL_AAPL', 'SEC_COMPANYFACTS', 'AAPL', 'Apple Inc. fundamentals', 'FUNDAMENTAL', '0000320193', '0000320193', 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('FUNDAMENTAL_MSFT', 'SEC_COMPANYFACTS', 'MSFT', 'Microsoft fundamentals', 'FUNDAMENTAL', '0000789019', '0000789019', 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('FUNDAMENTAL_NVDA', 'SEC_COMPANYFACTS', 'NVDA', 'NVIDIA fundamentals', 'FUNDAMENTAL', '0001045810', '0001045810', 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_CPI', 'FRED', 'CPI', 'Consumer Price Index', 'MACRO', 'CPIAUCSL', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH_ATTRIBUTION_REQUIRED', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_UNRATE', 'FRED', 'UNRATE', 'Unemployment Rate', 'MACRO', 'UNRATE', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH_ATTRIBUTION_REQUIRED', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_DFF', 'FRED', 'DFF', 'Effective Federal Funds Rate', 'MACRO', 'DFF', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH_ATTRIBUTION_REQUIRED', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_DGS10', 'FRED', 'DGS10', '10-Year Treasury Yield', 'MACRO', 'DGS10', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH_ATTRIBUTION_REQUIRED', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_DGS2', 'FRED', 'DGS2', '2-Year Treasury Yield', 'MACRO', 'DGS2', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH_ATTRIBUTION_REQUIRED', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_T10Y2Y', 'FRED', '10Y2Y', '10Y–2Y Treasury Spread', 'MACRO', 'T10Y2Y', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH_ATTRIBUTION_REQUIRED', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_GDP', 'FRED', 'GDP', 'Gross Domestic Product', 'MACRO', 'GDP', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH_ATTRIBUTION_REQUIRED', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_DOLLAR', 'FRED', 'USD', 'Broad U.S. Dollar Index', 'MACRO', 'DTWEXBGS', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH_ATTRIBUTION_REQUIRED', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z'),
  ('MACRO_TREASURY_DEBT', 'US_TREASURY_FISCALDATA', 'USDEBT', 'Total Public Debt Outstanding', 'MACRO', 'Debt to the Penny', NULL, 86400, 'PRIVATE_FOUNDER_RESEARCH', 1, 'NON_RAB1_RESEARCH_ONLY', 'NONE', '2026-08-13T00:00:00.000Z');

INSERT INTO research_provider_state (
  provider_id, instrument_id, status, next_due_at, detail_code, quota_state,
  rights_classification, updated_at, boundary, authority_effect
)
SELECT provider_id, instrument_id, 'PENDING', '2026-08-13T00:00:00.000Z',
  'AWAITING_FIRST_COLLECTION', 'WITHIN_CONFIGURED_BUDGET', rights_classification,
  '2026-08-13T00:00:00.000Z', 'NON_RAB1_RESEARCH_ONLY', 'NONE'
FROM research_instruments;
