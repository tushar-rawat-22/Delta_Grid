# Durable Observation Orchestrator v1

Mission 97 adds one local, durable, foreground observation workflow over the
Mission 96A read-only Research Control Plane. It records workflow history in a
separate SQLite database and publishes immutable local JSON artifacts. It does
not reopen research or authorize market data, protected data, model training,
signals, trading, exchanges, credentials, or capital.

The machine authority is
[`DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR_V1.json`](../contracts/DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR_V1.json).
That contract and the final freeze control any conflict with this explanation.

## Fixed workflow

`RESEARCH_OBSERVATION_REFRESH_V1` contains exactly three serial steps:

1. capture a Mission 96A snapshot through `ReadOnlyTrialLedger`,
   `ResearchControlPlaneService`, and `ControlPlaneSnapshot.as_dict()`;
2. independently verify the snapshot bytes, projection hashes, snapshot
   identity, repository identity, governance identities, and authority
   projection;
3. publish a deterministic observation manifest that links the accepted
   snapshot and verification receipts.

There is no caller-defined workflow, action identifier, branching, parallelism,
loop, plugin, Python module, shell command, subprocess, Git operation, network
endpoint, daemon, timer thread, scheduler, or background mode.

## Durable boundaries

Initialization binds the database to one canonical output root and one
governance repository root. Later commands accept only the database path and
load both roots from hash-verified immutable metadata. Every production open
verifies the complete Mission 93–97 contract chain and the Mission 96A
functional dependency.

Runs and receipts are immutable. Events are append-only. Status is derived from
verified events and the current ephemeral claim; there is no mutable
authoritative status column. Claims use bounded leases, monotonically increasing
fencing epochs, derived private fencing tokens, and stale-worker rejection.
Public status never exposes fencing tokens, claim hashes, or idempotency
material.

The database uses SQLite `DELETE` journal mode, `EXTRA` synchronous durability,
foreign-key enforcement, exact integer millisecond busy timeouts, and
`BEGIN IMMEDIATE` for every mutation. Each operation opens and closes its own
connection; connections are never shared between worker threads.

Each step permits at most three attempts. Retryable attempt 1 waits five
seconds, retryable attempt 2 waits thirty seconds, and attempt 3 is terminal.
Production service code never sleeps. Operators progress work explicitly with
`tick`, `recover`, or `run-until-idle`.

## Capture semantics

`observation_as_of` is the explicit Mission 96A snapshot and incident
timestamp. It is not a promise that the mutable source database is historically
filtered to that timestamp.

Before the first snapshot artifact is published, the upstream read-only
research state may legitimately change. If interruption leaves no final
artifact, a retry may capture a later valid state. The first successfully
published and verified snapshot artifact becomes authoritative for that run.
Every later replay verifies and reuses its exact bytes; it is never overwritten.

The supported guarantee is one accepted immutable receipt per step, derived
no-clobber artifact paths, safe replay, stale-worker rejection, and bounded
retries. It is not a claim of global exactly-once execution.

Filesystem publication and SQLite receipt persistence are separate recoverable
durability boundaries. A crash before publication leaves no accepted final
artifact. A crash after publication but before receipt persistence is recovered
by verifying and adopting the exact existing bytes. `completed_at` records the
explicit operational time when the receipt is actually persisted, so crash
adoption may legitimately produce a later value. No earlier receipt exists in
that window, and no hypothetical uncommitted receipt identity is claimed.

## Local CLI

Use `python -m offchain.orchestration` with one of:

- `init`
- `create-observation-run`
- `tick`
- `recover`
- `run-until-idle`
- `status`
- `cancel`

All time passed to the service is explicit. Only the CLI composition layer may
read current UTC when `run-until-idle` omits `--now`. Commands remain bounded
and foreground; reaching a future retry time requires another operator call.

Stopping calls to `tick` is the supported operational pause. There are no
pause or resume mutations.

## Permanent authority boundary

The artifacts are observation records only. They do not calculate or reinterpret
P&L, benchmark performance, fees, slippage, drawdown, exposure, turnover,
concentration, or trade counts. They do not rank trials or results. Successful
software verification does not establish profitable alpha and does not
authorize research, validation or holdout access, model training, signals,
portfolio construction, paper trading, live trading, exchange access,
credentials, capital deployment, or autonomous execution.
