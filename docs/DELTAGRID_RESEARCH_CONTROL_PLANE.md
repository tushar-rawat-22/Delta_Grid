# DeltaGrid Research Control Plane v1

Mission 96A adds the backend observation boundary required before any Research
Cockpit UI can exist. It opens an already-existing Mission 94/95 SQLite ledger
in true read-only mode and produces deterministic, JSON-compatible operator
snapshots. It cannot reserve a trial, append an event, finalize a result, or
change the database schema.

The controlling machine-readable contract is
`contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json`. Its authority is narrow:
read budgets, reservations, events, and immutable result links; load linked
results through Mission 95's `load_linked_result()` verifier; project those
verified values; and report integrity incidents. Mission 96A does not authorize
the Mission 96B UI.

## Read-only database boundary

`ReadOnlyTrialLedger` is independent of the write-capable `TrialLedger`. Before
opening SQLite it resolves an existing regular file and rejects symbolic links
in both the database path and its parent components. A missing path is rejected
and is never created.

SQLite is opened with the URI
`file:<percent-encoded-absolute-path>?mode=ro`, `uri=True`, and
`isolation_level=None`. Every connection sets `PRAGMA query_only = ON` and
`PRAGMA foreign_keys = ON`. A short read transaction binds the multiple ledger
queries used for one snapshot. Required tables, columns, declared types,
canonical hashes, deterministic trial IDs, event IDs, and result links are
verified before their values become projections.

One short transaction captures every budget, reservation, event, and result
link used by a snapshot. Result projection then gives Mission 95 an immutable
in-memory view of that captured state; Mission 95 may open its linked
artifacts, but it cannot reopen the ledger. Counts, lifecycle checks, trial
rows, and result-link verification therefore share one historical ledger
state.

The schema check also binds the authoritative primary keys, required
`NOT NULL` declarations, canonical unique identities, foreign keys,
immutability triggers, and reservation budget guard. A read-only
`foreign_key_check` runs inside the capture transaction. The adapter never
migrates or repairs an incompatible ledger.

## Snapshot and result authority

The caller supplies an explicit normalized UTC `as_of` timestamp and an
expected 40-character lowercase repository commit. Production code does not
run Git or read a wall clock. Given identical ledger bytes, linked artifacts,
repository commit, paths, and `as_of`, serialization is byte-identical.

The snapshot contains `schema_version`, `snapshot_id`, `snapshot_version`,
`system`, `trials`, `results`, `incidents`, and `canonical_snapshot_hash`.
Trials are ordered only by reservation time and trial ID. No performance value
affects ordering.

All persisted ledger timestamps use exact UTC ISO-8601 text ending in `Z`,
with either no fraction or one through six fractional digits. Calendar and
clock validity are parsed without local-time conversion or floating-point
arithmetic. Parsed UTC values—not raw timestamp strings—control lifecycle and
reservation ordering. Results follow their corresponding chronological trial
projections.

Mission 95's `load_linked_result()` remains the authority for completed result
artifacts. Mission 96A copies its verified bundle values, including metrics,
benchmark, costs, risk measures, timing diagnostics, protected-access counts,
artifact declarations, warnings, and verification declarations. It does not
reopen synthetic fixtures and does not recalculate any quantitative metric.

## Integrity incidents and health

The control plane detects unavailable or incompatible ledgers, malformed
canonical rows, invalid lifecycle histories, missing or mismatched result
links, missing or tampered artifacts, unsupported result schemas, failed
verification, and duplicate or conflicting identities. Safe row-local failures
become deterministic incidents while other valid trials remain visible.
Conditions that prevent trustworthy database access fail the complete snapshot
closed.

Health is one of `HEALTHY`, `DEGRADED`, `INTEGRITY_FAILURE`, or `UNAVAILABLE`.
Incident detection time is always the supplied `as_of`; no incident uses the
machine clock.

## Repository governance verification

The service rejects a missing, non-directory, or symlinked repository root.
Before serving snapshots it strictly reads and independently re-hashes the
Mission 93, 94, 95, and 96A governance contracts beneath that root. UTF-8 BOMs,
duplicate JSON object names, non-finite numbers, malformed objects, incorrect
contract identities, broken canonical hashes, and predecessor-chain mismatches
fail construction with `REPOSITORY_CONTRACT_INTEGRITY_FAILURE`.

The system projection contains a deterministic repository-root path identity
and deeply immutable verification declarations for all four contracts and
their predecessor chain.

Ledger and service composition identities are exposed only through read-only
properties. Public projection models detach caller containers: incident IDs and
snapshot collections are retained as tuples, while serialized mappings remain
deep copies. This is supported-API integrity discipline, not a cryptographic
object-isolation claim.

## Authority remains closed

The snapshot visibly states the fixed Mission 96A authority. Only read-only
ledger access, linked-result loading, and deterministic projection are true.
Ledger writes, admission, execution, strategy research, market data,
validation, holdout and protected data, model training, exchanges, paper or
live trading, capital, autonomous activity, and cockpit UI implementation all
remain false.
