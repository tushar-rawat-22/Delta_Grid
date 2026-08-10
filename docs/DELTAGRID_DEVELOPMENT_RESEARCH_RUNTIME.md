# DeltaGrid Development Research Runtime

## Status and authority

Mission 102 implements the first result-bearing runtime permitted after the
final freeze, but only for an exact `REAL_MARKET_DEVELOPMENT` trial already
admitted by Mission 101. It does not validate a strategy, open holdout data,
train a model, select or promote a candidate, paper trade, live trade, access
an exchange or credentials, place an order, or deploy capital.

No real Mission 102 research was executed while this runtime was implemented.
The production experiment registry contains zero economic families, so the
production execute command currently fails closed with
`EXPERIMENT_FAMILY_NOT_REGISTERED` after safe metadata binding and before it
opens market values. There is still no validated profitable strategy and no
selected candidate.

## Secure execution chain

The runtime accepts authority only through an independently certified Mission
101 release and exact development descriptor, a founder-issued permit, the
exact append-only permit-consumption row already created for this trial, the
exact Mission 94 reservation and Mission 101 `ADMITTED` event, and an
independently observed clean repository at the permit-bound commit.

Mission 102 opens a fresh read-only Mission 101 transaction, establishes its
SQLite snapshot with a real table read, and only then samples the trusted
authority decision time. Issuance and expiry are evaluated at that time, while
any revocation visible in the established snapshot rejects current execution.
It intentionally does not call Mission 101's normal
new-permit verification path. That path treats a fully consumed permit as
exhausted, which is correct for a new reservation. Mission 102 instead proves
that this trial owns the immutable consumption. A budget-one permit with one
consumed slot can execute its owner trial; another trial cannot borrow the
slot, and Mission 102 never consumes another slot.

For a current-authority check, any valid `REVOKED` event visible in that
database snapshot rejects execution even if a caller supplies an earlier
decision timestamp. Historical replay uses a separate non-current check and
continues to reconstruct the causal facts bound into a completed result.

Execution authorization linearizes at the successful authority snapshot.
Revocation committed before it prevents execution. Revocation committed after
it does not retroactively stop the already-running process. A restarted process
must take a new snapshot, so it cannot resume after later revocation merely
because an execution-spec file exists. Completed verified results remain
readable after later revocation.

Mission 94 and Mission 101 remain separate databases; Mission 102 does not
claim cross-database atomicity. It preliminarily reads Mission 94, acquires the
trial lock, rereads one consistent Mission 94 snapshot, establishes and holds
the Mission 101 snapshot, and performs a final consistent Mission 94 gate while
that Mission 101 snapshot remains active. The final state must still be the
exact admitted binding with no result link. Reservation, admission, and permit
consumption timestamps must be identical.

## One trial, one variant

Before any selected market value is opened, the runtime atomically claims a
canonical `execution-spec.json`. It binds the trial, permit consumption,
dataset, release, repository commit, registry and family hashes, the exact
variant selected by `declared_trial_number`, and all accounting, cost,
exposure, funding, and fill assumptions. Identical bytes can serve as recovery
evidence only after a fresh authority check. Different bytes fail with
`EXECUTION_SPEC_CONFLICT`.

The specification persists the reconstructable execution authority proof,
including the actual Mission 102 authority decision time, immutable Mission 94
binding hash, exact permit and consumption, and the complete sealed registry
snapshot core and hash. It does not substitute the earlier admission time or
mutable future consumption totals.

A private OS-level per-trial lock covers binding, specification claim,
execution, publication, verification, and Mission 94 finalization. The sealed
registry is future-extensible: a reviewed future commit may add a bounded family
and preregistered variant plan, but that new HEAD requires a new exact Mission
101 permit. The production CLI cannot load modules, paths, plugins, URLs, shell
commands, provider code, or test adapters.

Trial lock names accept only the exact Mission 94 identity shape
`trial-` plus 32 lowercase hexadecimal characters. Validation occurs before
any lock-file operation; containment, no-follow open, descriptor-based mode
setting, and regular-file checks fail closed on traversal and symlink input.
Syntactically valid but unknown trials create no lock file. New lock creation
uses a fixed short coordination lock so concurrent different-trial creators
cannot exceed the resource ceiling; existing per-trial locks remain usable at
the ceiling and do not serialize unrelated executions.

## Causal data, fills, and funding

The selected-value loader recertifies the exact Mission 101 release, verifies
the descriptor, reopens the embedded immutable Mission 100 backup, verifies the
source journal and identities, and strictly parses only selected payload JSON.
It cannot read mutable Mission 100 state, follow a newer release, reconstruct
missing data, or use the network.

Each variant declares exact observable `stream:symbol` pairs. The loader still
recertifies the full descriptor record-set identity, but it opens and discloses
payloads only for those exact pairs. Extra descriptor evidence is invisible to
both the adapter and accounting kernel, while a missing required stream, symbol,
or exact observable pair fails closed.

Events become visible at `available_at` and are ordered by availability time
then custody-record hash. An adapter receives only the current event and
bounded immutable state derived from already revealed events.

`NEXT_ELIGIBLE_BAR_CLOSE_V1` fills an intent only at the close of the first
later-revealed tradable bar whose close time is strictly later than the decision
availability time. It cannot fill on the decision bar, use an earlier open,
interpolate high or low, or synthesize an end-of-data fill.
Target notional means desired marked exposure at that unadjusted benchmark
close. Desired quantity and trade direction are computed once from the
benchmark; slippage changes execution cash economics only and cannot reverse a
reduction. A zero quantity delta resolves without a fill or costs.

Funding has separate economic and recognition times. When a funding record is
revealed, the kernel applies its verified rate and mark price to the position
economically effective at `funding_time_ms`. A positive rate means a long pays
and a short receives.
The benchmark close supplies a simulated fill price, but a position cannot
become effective before its fill evidence is public. Its effective UTC
millisecond is the later of benchmark close time and conservatively
ceiling-normalized evidence availability.
Funding uses only positions effective by `funding_time_ms`, so delayed evidence
never backdates funding or rewrites earlier adapter-visible state. This is a
conservative public-evidence simulation rule, not an exchange-receipt claim.

## Accounting, artifacts, and CLI

Adapters emit only bounded target-exposure research intents. The central
kernel alone calculates fills, fees, slippage, funding, positions, cash,
equity, PnL, turnover, exposures, peaks, and drawdown using `Decimal` values
constructed from verified strings. Spot is long-or-flat only; perpetual
research instruments may be long, short, or flat. Mark, index, and funding
streams are informational and cannot be traded. Positions, bounds, pending
intents, fills, and marks use exact `stream:symbol` identities, so spot and
perpetual positions for the same symbol remain independent and informational
mark/index bars cannot revalue a tradable position. Initial research NAV must
be positive, fee basis points are bounded from 0 through 10,000 inclusive, and
slippage basis points are bounded from 0 inclusive to 10,000 exclusive.
All authoritative arithmetic uses the explicit
`DELTAGRID_M102_DECIMAL_CONTEXT_V1`: precision 50, round-half-even, fixed
exponent limits, complete trap policy, and cleared flags. Ambient process
Decimal settings cannot change specifications, ledgers, results, or hashes.

The private result runtime defaults to `~/.deltagrid/development_results`, but
implementation tests use temporary private directories. It stores one
execution specification, compact event ledger, and result bundle per trial.
An independent verifier reloads persisted bytes, reopens upstream evidence,
and recomputes the result before the existing Mission 94 ledger is atomically
linked and completed with `M102_DEVELOPMENT_RESULT_VERIFIED`.
The authority decision time remains the snapshot time. Completion and failure
events use a fresh trusted audit time and cannot be earlier than the preceding
trial lifecycle event.
Public result verification requires the completed event and its one exact
canonical result link in a consistent Mission 94 snapshot. The execution path
uses an explicit internal pre-finalization replay, finalizes atomically, and
then performs public finalized replay before returning success.

Full replay is permitted only from an independently observed clean HEAD equal
to the repository commit bound by the exact permit. A newer HEAD fails with
`HISTORICAL_EXECUTION_CODE_CONTEXT_REQUIRED`; Mission 102 neither checks out nor
dynamically loads historical code. Nested strategy parameters are recursively
copied and frozen, and changing economics requires a new immutable family or
variant identity.

The canonical entry point is:

```bash
python -m offchain.research.development_runtime --help
```

Mission 103 remains the next validation and statistical-promotion governance
mission. Mission 105 remains the later paper-execution mission. Neither is
authorized here.
