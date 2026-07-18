# ADR-0044: Shadow Observation Close Eligibility Engine

<!-- deltagrid-document-status: HISTORICAL -->

> **Historical architecture decision**
>
> This ADR records a decision accepted for the DeltaGrid phase in which it was
> written. “Accepted” does not grant current research, paper trading, live
> trading, capital, ML, or autonomous authority. See the
> [documentation home](../README.md) and
> [final freeze](../DELTAGRID_FINAL_FREEZE.md) for current status.

## Status

Accepted

## Context

Mission 43 added break-even timing for shadow observations.

DeltaGrid now needs a structured close eligibility layer that converts break-even status into continue, close-eligible, reject, risk-review, or safety-block decisions.

## Decision

Add a shadow observation close eligibility engine.

Files:

- offchain/backtest/shadow_observation_close_eligibility_engine.py
- offchain/tests/test_shadow_observation_close_eligibility_engine.py

Code commit:

- 110723d Add shadow observation close eligibility engine

The engine reads:

- shadow_observation_break_even_tracking

The engine writes:

- shadow_observation_close_decisions
- shadow_observation_close_decision_reports

It evaluates:

- break-even status
- remaining hours to break-even
- cost remaining
- expected net PnL
- risk flags
- safety state
- close eligibility
- uneconomic rejection

## Safety

The close eligibility engine is shadow-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All decisions must preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Verdict

Mission 44 improves close/continue/reject decision quality.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Continue shadow research and outcome decision infrastructure.
