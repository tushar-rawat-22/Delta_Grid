# Safety invariants

## Current boundary

DeltaGrid is frozen as a completed quantitative research platform with no
validated profitable strategy and no selected candidate. Alpha discovery is
stopped. Paper trading and live trading are not authorized, and capital
deployment is blocked.

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
- Historical records cannot override the later controlling contract.

## Changing an invariant

Changing an invariant requires a versioned policy and authorization process.
A capital-readiness review alone cannot change a boundary, nor can a score,
test result, model recommendation, code change, or user-interface action.

A future change applies prospectively within its explicit scope. It must not
rewrite an established research outcome, metric, protocol, identity, access
record, or decision.

## Current non-authorizations

The current policies do not authorize new research, validation or holdout
access, ML work, paper or dry-run operation, live trading, orders, private-key
or account access, capital deployment, or autonomous promotion and execution.
