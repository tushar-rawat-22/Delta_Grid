# ADR-0089: End-to-End Baseline Strategy Falsification

<!-- deltagrid-document-status: HISTORICAL -->

> **Historical architecture decision**
>
> This ADR records a decision accepted for the DeltaGrid phase in which it was
> written. “Accepted” does not grant current research, paper trading, live
> trading, capital, ML, or autonomous authority. See the
> [documentation home](../README.md) and
> [final freeze](../DELTAGRID_FINAL_FREEZE.md) for current status.

Date: 2026-07-12

Status: Accepted after verification

## Context

Missions 85 through 88 locked the funding-carry hypothesis, captured and
certified the required public data, and created an assumption-bounded execution
cost model. None of those missions established net alpha.

Mission 89 must answer one economic question in one coherent block: whether one
of the twelve preregistered deterministic variants survives development
selection and fixed validation after conservative costs without using the
untouched holdout.

## Decision

Mission 89 combines the evaluation protocol, mathematical feasibility screen,
strict next-bar event simulation, cash-flow ledger, all twelve development and
validation evaluations, candidate selection, parameter-neighbourhood checks,
concentration checks, volatility-regime checks, PBO, deflated-Sharpe quality,
notional sensitivity, cost stress, and final strategy decision.

The primary profile is USD 10,000 per leg. USD 1,000 and USD 50,000 are
sensitivity profiles. Normal costs are the base case, conservative costs are the
mandatory promotion gate, and severe costs are diagnostic only.

The funding settlement that triggers an entry is not collectible. Entries,
exits, and rebalances execute strictly at the next hourly bar open.

## Holdout Boundary

Mission 89 may query development and validation only. The untouched holdout is
sealed for Mission 90 and may not be used for selection, tuning, replacement,
or diagnostics.

## Decisions

Mission 89 returns exactly one of:

- `ADVANCE_TO_MISSION90_UNTOUCHED_HOLDOUT`
- `CONTINUE_COLLECTING_EVIDENCE_NO_HOLDOUT_ACCESS`
- `REJECT_AND_ARCHIVE_FUNDING_CARRY`

A rejected strategy is not rescued through machine learning, cost reduction,
asset removal, or post-validation tuning.

## Safety

Mission 89 performs offline research only. It does not authorize live signals,
orders, private keys, signing, leverage deployment, model promotion, capital
deployment, or a forward-profitability claim.
