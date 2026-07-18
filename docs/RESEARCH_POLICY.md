# Research policy

## Purpose

This current internal policy governs how DeltaGrid converts an economic idea
into reproducible evidence and a documented decision. It protects the quality
of that decision; it does not authorize research or trading.

The [final freeze](DELTAGRID_FINAL_FREEZE.md) controls present project status.
The deterministic contract is
[`DELTAGRID_FINAL_FREEZE_V1.json`](../contracts/DELTAGRID_FINAL_FREEZE_V1.json).

## Current state

DeltaGrid is a completed quantitative research platform with no validated
profitable strategy and no selected candidate. Alpha discovery is stopped.
Paper trading and live trading are not authorized, and capital deployment is
blocked.

New strategy work requires genuinely new evidence and a new versioned
reopening contract. Historical next actions, available code, and previously
implemented research infrastructure do not reopen the programme.

## Research-First Operating Model

Research must establish a falsifiable economic hypothesis before
implementation. Evidence determines whether the hypothesis survives; the
desire for a passing candidate must never determine the protocol.

This heading is retained because repository checks use it to identify the
policy. It does not revive the historical sequence that once followed it.

## Research principles

- State the economic mechanism and a plausible reason for persistence before
  writing strategy logic.
- Preregister the protocol, candidates, data boundaries, costs, statistical
  controls, and decision gates before inspecting outcome-bearing results.
- Fix candidate, parameter, feature, and model budgets in advance. Every
  result-guided attempt consumes that budget.
- Use only information causally available at the decision timestamp.
- Make results reproducible from versioned code, data identities, assumptions,
  and protocols.
- Treat rejection, expiration, and an inconclusive result as valid outcomes.
- Never lower or replace a gate after observing the result it governs.

## Research stages

A future reopening contract may define the following sequence:

1. Feasibility of the economic mechanism and required causal data.
2. Data certification, provenance review, and immutable data identity.
3. Development testing within a fixed experiment budget.
4. One fixed validation evaluation for an eligible development survivor.
5. One opening of a sealed holdout after all earlier gates pass.
6. Independent ledger parity and lookahead, recursive, or other bias analysis
   where the protocol requires them.
7. Forward paper evaluation under a separate, explicit authorization.
8. Proof-capital and live stages under distinct later authorizations.

Listing a stage describes possible future controls; it does not authorize the
stage. Moving from research to validation, holdout, paper, proof-capital, or
live operation always requires the authorization and evidence specified for
that boundary.

## Data boundaries

Development, validation, and holdout data serve different purposes and must
remain separated. Development may support selection only within the frozen
budget. Validation may test a fixed eligible survivor. A sealed holdout may be
opened once and only after every preceding gate passes.

Validation and holdout access require explicit authorization. Protected data
must not be viewed, summarized, queried, or used indirectly as a selection
oracle before that authorization exists.

Every dataset must retain its source, acquisition time, first-availability
time, transformations, corrections, coverage, and deterministic version or
identity. Features may contain no future information. Missing, late,
inconsistent, or retrospectively corrected critical data must trigger the
contract's rejection or pause rule rather than an undocumented repair.

## Costs and execution assumptions

Research decisions must use net performance. Every relevant simulation must
include fees, spread, slippage, latency, and a documented capacity or
market-impact assumption. Standard and stress scenarios must show whether the
result depends on an unrealistically favorable execution model.

Cost assumptions must be fixed before the results they evaluate. Gross returns
may be reported for diagnosis, but they cannot support promotion.

## Statistical controls

Each protocol must define a minimum sample size and apply a multiple-testing
correction that covers all result-guided attempts. Appropriate null controls,
independent replication, concentration analysis, parameter sensitivity, and
chronological or regime stability checks are required.

A result that depends on a small number of observations, one asset, one period,
one narrow parameter choice, or one optimistic cost scenario must fail or be
classified as inconclusive under the frozen rules. Statistical significance
alone does not establish a durable economic edge or future profitability.

## Promotion and rejection

A candidate advances only when it passes every fixed gate for its current
stage. A pass does not skip the next authorization boundary and does not create
paper, capital, or live authority.

Failure leads to rejection, archiving, or expiration as defined by the
protocol. It must not trigger automatic optimization, candidate replacement,
or repeated rescue cycles until a passing result appears. Negative outcomes
remain part of the evidence record.

## ML and AI

ML research and model training are not currently authorized. Any future ML
work must be expressly included in a versioned reopening contract and follow
the [ML research adapter](DELTAGRID_ML_RESEARCH_ADAPTER.md).

No model or AI component may select its own scope, change its evaluation
policy, refresh protected data, promote itself, authorize capital, or place an
order. Model output is evidence for a controlled decision, not authority.

## Evidence and audit trail

Each authorized experiment must preserve:

- the strategy and implementation version;
- the preregistered protocol and experiment budget;
- data identities, provenance, and protected-data access records;
- cost and execution assumptions;
- complete result and failure records;
- the decision and the gate responsible for it; and
- hashes needed to verify the published artifacts.

Evidence must remain sufficient for an independent reviewer to reproduce the
decision. Style edits must never rewrite raw results, protocols, hashes,
access counts, or negative outcomes.

## Reopening research

The [future strategy intake policy](FUTURE_STRATEGY_INTAKE_POLICY.md) defines
the intake gate. Genuinely new information, an overlap audit, and a new
versioned reopening contract are required before implementation or
result-bearing research begins.

A reopening contract authorizes only its stated scope. It cannot implicitly
authorize validation, holdout, paper evaluation, ML, capital, or live trading.

## What this policy does not authorize

This policy does not authorize:

- new strategy research or backtesting;
- validation or holdout access;
- paper trading or dry-run operation;
- live trading or order placement;
- capital deployment;
- ML implementation, training, or evaluation; or
- autonomous execution or promotion.
