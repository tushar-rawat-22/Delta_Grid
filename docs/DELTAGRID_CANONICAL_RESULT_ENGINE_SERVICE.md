# DeltaGrid Canonical Result Engine Service

## Purpose

Mission 95 adds one deterministic service after the Research Admission Core.
It can execute the four existing non-alpha controls over an admitted,
hash-bound synthetic fixture, write and verify canonical artifacts, and link
the verified result to the admitted trial.

The controlling contract is
`contracts/DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE_V1.json`. Its exact stage is
`MISSION_95_SYNTHETIC_CONTROL_EXECUTION`.

The contract base commit identifies the repository state on which Mission 95
was designed. It is not the implementation commit recorded in future results.
The trusted composition root supplies that runtime implementation commit as
exactly 40 lowercase hexadecimal characters when constructing the service.
Production code does not invoke Git or a subprocess to discover it. The
publication commit cannot be hard-coded during development because it does not
exist yet.

Golden hashes in the focused tests identify deterministic test vectors. They
are not claims about the future publication commit or future result files.

## Authority boundary

The service is not a general research or execution engine. Only
`SYNTHETIC_FIXTURE` data with the `SYNTHETIC_DEVELOPMENT` split can pass. The
fixed dispatcher contains `NO_TRADE_CONTROL`, `BUY_AND_HOLD_CONTROL`,
`SEEDED_RANDOM_CONTROL`, and `SIMULATOR_STATE_MACHINE_CONTROL`.

The Mission 94 control record still says `execution_authorized=false`; that
registry describes a control but grants no authority. Mission 95 creates a
hash-bound permit with the narrower
`MISSION_95_SYNTHETIC_CONTROL_ONLY` scope after secure binding.

General controls, strategy research, market data, development-market
evaluation, validation, holdout, protected data, historical backtests and
simulators, model training, paper or live trading, exchange or credential
access, autonomous work, and capital deployment remain unauthorized.

Mission 95 closes Mission 93 GAP-01 and GAP-05 only for admitted synthetic
non-alpha controls. It does not authorize the Mission 96 dashboard, strategy
research, market data, protected splits, ML, exchange access, paper trading,
live trading, autonomy, or capital.

## Secure binding

A trial becomes securely bound only after the service has verified the exact
request and decision schemas and hashes, reconstructed the Mission 94 decision
ID, matched the runtime implementation commit and clean flag, recomputed the
deterministic trial ID, matched every reservation field, verified the budget
hash and exact Mission 95 experiment family, re-resolved the dataset, and
revalidated the control.

Malformed, forged, or mismatched input before that point writes no lifecycle
event. Fixture bytes are not opened until after secure binding. A genuine
fixture, execution, artifact, result, or later integrity failure can then close
the still-admitted trial with one `FAILED` event.

## Fixture verification and limits

The admission resolver remains metadata-only. The engine receives its read-only
artifact root, resolves the admitted relative path beneath that root, rejects
traversal, symlinks, missing or non-regular files, and opens the fixture once.
It verifies the SHA-256 digest of the exact file bytes before strict JSON
decoding.

The fixture mapping validator is also reusable without file access. When a
persisted result is loaded, the verifier rebuilds the original fixture mapping
from the dataset fields and the fixture-derived columns in event-ledger order.
It applies the same exact schema, identifier, timestamp, bound, uniqueness, and
canonical-hash checks used by the source loader. It then reconstructs the
canonical fixture hash and the SHA-256 digest of the complete canonical fixture
bytes. This lets completed replay remain verifiable after the source fixture
has been removed.

Fixture JSON must be compact canonical UTF-8 without a BOM, duplicate keys,
non-finite numbers, missing fields, extra fields, or wrong exact types.
Timestamps increase strictly in normalized UTC order. Event IDs are unique and
fixture accounting values are bounded.

The fixed limits are 512 events, signed-64-bit maximum positive accounting
inputs (`9223372036854775807`), and 1,048,576 bytes each for the fixture, event
ledger, and result bundle. Generated artifacts are checked against their limits
before publication.

## Deterministic accounting

The service uses one integer-only long-or-flat kernel. Every event records the
target, attempted and filled delta, execution price, fee, slippage, position,
gross and net cash, gross and net equity, turnover, and state transition. Fill
availability truncates deterministically toward zero; buy slippage rounds
upward, sell slippage rounds downward, and fees use ceiling integer arithmetic.

Every run must finish flat. The bundle reports explicit gross and net results,
fees, slippage, drawdown, turnover, exposure, concentration, attempts, fills,
trades, and final state. Funding, borrowing, impact, latency, and all
unauthorized access counters are explicit zeroes. A fixed buy-and-hold result
from the same kernel appears only as a `NON_TRIAL_BASELINE`; it is not another
trial or a profitability claim.

## Canonical artifacts and result status

Artifact names never come from the request. A validated trial ID determines:

- `<result_root>/<trial_id>/event-ledger.json`
- `<result_root>/<trial_id>/result.json`

Each artifact is compact canonical JSON and carries a canonical content hash.
The bundle also carries the event ledger's relative path, byte digest, and
canonical digest. Writes use a flushed and `fsync`ed same-directory temporary
file followed by immutable publication. Identical existing bytes are a
recoverable replay; different existing bytes fail closed.

The result bundle binds the Mission 95 contract, implementation repository,
request, decision, reservation, budget, dataset, fixture, control, permit,
engine, kernel, artifact, and execution identities. It always carries:

- `SYNTHETIC_ONLY_NON_ALPHA_CONTROL`
- `NO_PROFITABILITY_INFERENCE`
- `NO_RESEARCH_TRADING_OR_CAPITAL_AUTHORITY`

The bundle records result authority, not the SQLite trial transition. Its
`result` section states `RESULT_VERIFIED /
SYNTHETIC_CONTROL_RESULT_VERIFIED`, uses the admitted request timestamp as the
deterministic `recorded_at`, and records the first and final fixture timestamps.
`failure_stop_or_rejection_reason` is JSON null for this verified success. The
bundle does not claim that the trial is already `COMPLETED`.

The engine section freezes these component identities:

- `DELTAGRID_MISSION95_CANONICAL_RESULT_ENGINE_V1`
- `DELTAGRID_SYNTHETIC_LONG_OR_FLAT_SIMULATOR_V1`
- `DELTAGRID_AVAILABLE_FILL_TARGET_DELTA_EXECUTION_MODEL_V1`
- `DELTAGRID_INTEGER_FEE_SLIPPAGE_COST_MODEL_V1`
- `DELTAGRID_INTEGER_DRAWDOWN_EXPOSURE_CONCENTRATION_RISK_MODEL_V1`

Timing diagnostics come only from adjacent normalized fixture timestamps.
Durations and minimum and maximum intervals use integer microsecond arithmetic;
they do not use wall-clock measurements, floating point, platform timestamps,
or local-time conversion.

It intentionally contains no Sharpe, Sortino, Calmar, DSR, PBO, p-value,
ranking, candidate-eligibility, selection, or promotion field.

## Persisted-link loader

The public application loader is:

`load_linked_result(*, result_root: Path | str, trial_ledger: TrialLedger,
trial_id: str) -> LinkedResult`

It accepts no caller-supplied expected identity dictionary or expected hashes.
It obtains the canonical result link and latest verified event from SQLite,
verifies the link, bundle, event ledger, fixed control, permit, engine, kernel,
warnings, zero prohibited-access counters, and cross-artifact identities, then
returns the immutable bundle with the authoritative persisted
`COMPLETED / SYNTHETIC_CONTROL_COMPLETED` lifecycle.

The verifier independently rebuilds the admitted request core from result
fields and requires its hash to match the admission request hash. It separately
requires the persisted reservation to carry that same admitted hash. It also
rebuilds the exact dataset-resolution core, including provenance, artifact
path, metadata identity, authorization stage, and reason, then matches both the
resolution hash and the admitted decision identity. A result that merely
rehashes its downstream fields cannot replace either upstream authority.

The bundle includes an ordered 33-entry `mission93_gap_05_field_map`, one entry
for every field in the Mission 93 cockpit charter. The entries contain only
fixed JSON paths, cardinalities, and direct grouping or singleton-projection
instructions; they contain no executable or UI behavior and require no metric
recalculation.

The loader deliberately does not recalculate fills, prices, fees, slippage,
cash, equity, results, drawdown, turnover, exposure, concentration, or benchmark
metrics. Those remain outputs of the one accounting kernel.

## Lifecycle and recovery

The service publishes the event ledger and result bundle, privately verifies
them against an internally constructed canonical link, and only then uses the
internal verified-result finalization path with that complete link object. That
path is intentionally absent from the supported public application API. One
`BEGIN IMMEDIATE` transaction inserts the link and appends
`COMPLETED / SYNTHETIC_CONTROL_COMPLETED`. The service finally reloads the
result through the public persisted-link loader.

An unlinked result file is recoverable orphan output. It is not an authoritative
completed Mission 95 result. Only a verified link plus the matching canonical
`COMPLETED` event makes the result authoritative.

Concurrent or later identical execution returns the same linked result without
adding an event. Bounded SQLite contention is reported explicitly, and an exact
retry can reuse orphan artifacts and complete the link. A completed replay
validates the supplied request, decision, reservation, and persisted result but
does not require the original fixture file to remain.

Mission 94's generic ledger continues to permit `ADMITTED → COMPLETED` for
compatibility. Such a generic completed trial has no loadable Mission 95 result
unless the verified Mission 95 link and matching completion event also exist.
A conflicting link or artifact fails closed, and a failed trial cannot be
rerun.

`ResultBundle` cannot be publicly constructed from arbitrary mappings or
bytes. Only the verified loading path can create one, and each `as_dict()` call
returns a new detached value. This is supported-API integrity discipline, not a
hostile-caller or cryptographic boundary.

If a securely bound failure cannot be persisted while the trial remains
admitted, the service raises `TRIAL_TERMINALIZATION_FAILED` and retains the
original engine reason in the error context.
