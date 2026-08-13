# Safety invariants

## Current boundary

DeltaGrid has no validated profitable strategy and no selected candidate. The
final freeze remains controlling except for narrow prospective authority
expressly granted by later versioned contracts. Mission 102 permits only an
exact consumed-permit-bound `REAL_MARKET_DEVELOPMENT` trial to execute; its
production registry initially contained zero economic families; RAB-1 now
prospectively registers exactly one four-variant family. Mission 103
permits only finite-program qualification infrastructure and separately
founder-authorized one-use protected-stage machinery. Both M103 production
registries now each contain one RAB-1 service, no RAB-1 result or protected execution exists, and its
maximum verdict has authority effect `NONE`. Paper trading
and live trading are not authorized, and capital deployment is blocked.

The [final freeze](DELTAGRID_FINAL_FREEZE.md) and its
[deterministic contract](../contracts/DELTAGRID_FINAL_FREEZE_V1.json) control
the present state. These invariants apply to the current repository version;
they do not claim that every possible future version must remain frozen.

## Non-Negotiable Safety Invariants

No review, readiness score, model output, passing test suite, or dashboard
action can change an authorization boundary by itself. This compatibility
heading remains because a repository check uses it to identify this policy.

An authorization change requires all of the following:

1. a new versioned controlling contract;
2. explicit approval for the specific stage;
3. the verification evidence required for that boundary; and
4. publication through the repository's controlled process.

## Authorization invariants

- Authorization is explicit; it is never inferred from silence, maturity, or
  a previous stage.
- Code existing in the repository does not authorize its operation.
- Passing tests verifies the tested properties and does not authorize research,
  protected-data access, trading, or capital.
- Historical plans and next actions do not override current contracts.
- No component, model, AI system, tool, or operator interface can authorize
  itself.
- A reopening contract authorizes only the exact work and stage it defines.

## Data invariants

- Validation and holdout data cannot be accessed without explicit
  authorization for that protected stage.
- Protected payload values cannot be loaded until the exact one-use founder
  authorization is consumed and `OPENED` is durably committed.
- Replication, validation and holdout scored records are pairwise disjoint,
  obey their frozen purge/gap/embargo, and begin from flat cash. Context does
  not produce scored PnL.
- Features and decisions may use only information available at the relevant
  decision timestamp; future information is prohibited.
- Dataset identities, provenance, availability times, transformations, and
  correction records must remain traceable.
- Missing, stale, inconsistent, or unverifiable critical data causes a
  fail-closed stop. It cannot be silently filled or bypassed to continue.

## Execution invariants

The current repository state prohibits live exchange orders, private-key use,
transaction signing, real-capital deployment, and unauthorized account or
exchange endpoints.

Paper execution is unavailable unless a versioned contract and a separate
stage-specific approval authorize it. Simulation or execution code does not
make paper operation available by itself.

## Risk invariants

- A missing, invalid, stale, or uncertain limit fails closed.
- No component may raise its own capital, exposure, leverage, position, order,
  drawdown, or loss limit.
- A safeguard cannot disable or bypass itself.
- Unresolved state, recovery, or reconciliation errors cause a pause.
- A risk breach must stop the affected activity and preserve an audit record.
- Resumption requires verified resolution and explicit reauthorization where
  the controlling policy requires it.

## AI and model invariants

- AI and models cannot promote a strategy or model.
- They cannot change policy, limits, gates, or protected-data boundaries.
- They cannot authorize capital or obtain direct order authority.
- They cannot choose training, feature, candidate, or evaluation scope outside
  an approved versioned contract.
- They cannot use later-stage results to authorize a rescue or repeated search.

The [ML research adapter](DELTAGRID_ML_RESEARCH_ADAPTER.md) describes a
possible future design. It does not currently authorize ML implementation,
training, evaluation, promotion, or trading.

## Evidence invariants

- Every decision must remain traceable to its protocol, inputs, results, gates,
  and authorization.
- Hashes, protocols, raw evidence, access counts, and deterministic records are
  not rewritten for readability or style.
- Rejections, inconclusive results, breaches, and other negative outcomes are
  preserved.
- Failed checks and abandoned attempts cannot be silently removed from the
  evidence or experiment budget.
- A failed, missing or crashed declared hypothesis remains in the complete
  program-wide multiplicity family. An exact retry gets neither fresh capacity
  nor fresh randomness.
- Historical records cannot override the later controlling contract.

## Changing an invariant

Changing an invariant requires a versioned policy and authorization process.
A capital-readiness review alone cannot change a boundary, nor can a score,
test result, model recommendation, code change, or user-interface action.

A future change applies prospectively within its explicit scope. It must not
rewrite an established research outcome, metric, protocol, identity, access
record, or decision.

## Current non-authorizations

The current policies authorize no research beyond the exact Mission 101,
Mission 102 and Mission 103 gates. Mission 103 infrastructure does not itself
open replication, validation or holdout; each future stage needs its exact
founder authorization. The policies do not authorize ML work, paper or dry-run
operation, live trading, orders, private-key or account access, capital
deployment, or autonomous promotion and execution.
