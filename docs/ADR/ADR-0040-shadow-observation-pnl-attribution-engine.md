# ADR-0040: Shadow Observation PnL Attribution Engine

## Status

Accepted

## Context

Mission 39 added lifecycle tracking for open shadow-paper observations.

DeltaGrid now needs cost-aware PnL attribution so that expected funding accrual can be compared against fees, spread cost, and slippage cost.

The system must remain safe and free.

## Decision

Add a shadow observation PnL attribution engine.

Files:

- offchain/backtest/shadow_observation_pnl_attribution.py
- offchain/tests/test_shadow_observation_pnl_attribution.py

Code commit:

- 34629c4 Add shadow observation PnL attribution engine

The attribution engine reads:

- shadow_observation_lifecycle_snapshots

The attribution engine writes:

- shadow_observation_pnl_attribution
- shadow_observation_pnl_attribution_reports

It calculates:

- gross expected funding PnL
- fee cost
- spread cost
- slippage cost
- total cost
- net expected PnL
- net expected return bps
- edge-to-cost ratio
- attribution status
- global attribution verdict

## Safety

The attribution engine is shadow-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All attribution records must preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Mission 40 Verification

Expected verification:

- Mission 40 unit tests pass
- full offchain suite passes
- PnL attribution reads Mission 39 lifecycle snapshots
- PnL attribution records persist in SQLite
- attribution report shows safety_breach_count = 0
- young observations may remain negative after cost

## Verdict

Mission 40 improves cost-aware shadow observation analysis.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Continue shadow research infrastructure.
