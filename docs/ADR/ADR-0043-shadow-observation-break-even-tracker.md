# ADR-0043: Shadow Observation Break-Even Tracker

## Status

Accepted

## Context

Mission 40 showed that current shadow observations are negative after costs.

DeltaGrid needs to know how long each observation must remain open before expected funding accrual can cover estimated fee, spread, and slippage costs.

## Decision

Add a shadow observation break-even tracker.

Files:

- offchain/backtest/shadow_observation_break_even_tracker.py
- offchain/tests/test_shadow_observation_break_even_tracker.py

Code commit:

- f880dd4 Add shadow observation break-even tracker

The tracker reads:

- shadow_observation_pnl_attribution

The tracker writes:

- shadow_observation_break_even_tracking
- shadow_observation_break_even_reports

It calculates:

- funding per hour
- total break-even hours
- remaining hours to break-even
- projected break-even timestamp
- cost remaining
- break-even status
- global break-even verdict

## Safety

The break-even tracker is shadow-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All records must preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Verdict

Mission 43 improves cost-aware observation timing.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Continue shadow research and cost-adjusted observation analysis.
