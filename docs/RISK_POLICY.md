# Risk policy

## Purpose

This current internal policy protects research integrity, operational safety,
and capital boundaries. It defines controls that must exist before a future
stage can operate; describing a control does not activate that stage.

The [final freeze](DELTAGRID_FINAL_FREEZE.md) controls the present state. The
[safety invariants](SAFETY_INVARIANTS.md) state the boundaries that every
component must respect.

## Current risk state

DeltaGrid has no approved strategy, no active paper portfolio, no live
positions, and no capital authorization. Paper execution, live execution, and
account operation are not authorized. Any related repository capability is
inactive, and its existence provides no authority.

## Live Trading Remains Blocked

Live trading is not authorized. This compatibility heading remains because a
repository documentation check identifies the risk policy by this phrase. It
does not describe an active trading system with a zero position.

## Core principles

- Fail closed when authority, data, limits, or system state is missing,
  inconsistent, stale, or uncertain.
- Give each component only the access needed for its authorized task.
- Define limits explicitly and treat a missing limit as a stop condition.
- Keep research promotion, stage authorization, and capital approval separate.
- Make decisions and state transitions reproducible from durable evidence.
- Never allow a component to expand its own scope or authority.
- Stop automatically when critical data or system health cannot be verified.

## Research risk

Research controls must address overfitting, repeated testing, data leakage,
weak sample size, regime instability, concentrated profit and loss, and
unrealistic execution costs. Candidate, feature, parameter, threshold, and
model attempts must remain within a preregistered budget and an appropriate
multiple-testing correction.

Promotion must depend on chronological evidence, realistic fees and execution
stress, null controls, replication, concentration, and parameter sensitivity.
A passing backtest or statistical test is evidence within its defined scope;
it is not proof of profitability and does not authorize another stage.

## Operational risk

Any future authorized operation must stop or pause on:

- stale, missing, duplicated, or inconsistent critical data;
- duplicate jobs, intents, or orders;
- clock drift, ambiguous timestamps, or broken event ordering;
- failed restart, state recovery, or reconciliation;
- unavailable or unverified dependencies;
- access to an endpoint outside the approved allowlist; or
- missing, incomplete, or unverifiable audit logs.

Recovery must not guess at positions, balances, orders, data freshness, or the
last completed action. Uncertain state remains stopped until reconciled from
an authoritative record.

## Future paper-stage controls

Paper operation is not currently authorized. If a later contract and
stage-specific approval authorize it, the stage must define a virtual-capital
ceiling, gross and net exposure limits, drawdown and daily-loss limits,
position limits, strategy expiration, and data-health gates.

The paper system must pause automatically on a breach or uncertain state and
reconcile its virtual orders, fills, positions, and balances before resuming.
Paper results remain evidence only; they cannot approve proof-capital or live
operation.

## Future proof-capital and live controls

Proof-capital and live operation are later stages and are not approved. Any
future authorization must be separate, versioned, time-bounded, and limited to
an explicitly approved capital ceiling, strategy, instrument set, and one or
more bounded venues.

Before activation, that later stage must provide order-rate and position
limits, loss and drawdown limits, a tested kill switch, reconciliation,
incident response, and human activation. It must grant no withdrawal authority
and no access to accounts or endpoints outside the approved scope.

Passing research, paper, or capital-readiness review cannot create this
authorization by itself.

## Authority separation

No system, model, AI component, operator tool, or dashboard may autonomously:

- increase capital, leverage, exposure, or loss limits;
- weaken, bypass, or disable a safeguard;
- approve or promote a strategy;
- reopen research or protected data;
- authorize its own stage or credentials; or
- change evaluation gates after observing results.

Authorization must come from the controlling versioned contract and explicit
stage-specific approval, supported by the required verification evidence.

## Breach response

A suspected breach requires an immediate stop. Preserve logs and evidence,
reconcile data and operational state, identify the cause and affected scope,
and document corrective action.

Operation may resume only after the breach is resolved, required controls are
verified, and explicit reauthorization is recorded. A restart, passing test,
or cleared alert is not reauthorization by itself.

## What this policy does not authorize

This policy does not authorize:

- strategy approval or promotion;
- paper trading or dry-run operation;
- live execution or order placement;
- capital allocation or deployment;
- custody or withdrawal access; or
- broker, exchange, or private account integration.
