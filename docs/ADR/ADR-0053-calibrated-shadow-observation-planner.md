# ADR-0053: Calibrated Shadow Observation Planner

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

Mission 52 found positive calibrated scenarios for BTCUSDT and ETHUSDT under low-cost and longer-holding assumptions. SOLUSDT remained rejected due to negative average funding.

DeltaGrid now needs a planner that converts viable calibrated scenarios into shadow-only observation plans.

## Decision

Add a calibrated shadow observation planner.

Files:

- offchain/backtest/calibrated_shadow_observation_planner.py
- offchain/tests/test_calibrated_shadow_observation_planner.py

Code commit:

- 4e821a6 Add calibrated shadow observation planner

The planner reads:

- cost_calibration_break_even_scenarios
- cost_calibration_break_even_reports

The planner writes:

- calibrated_shadow_observation_plans
- calibrated_shadow_observation_plan_reports

The planner selects:

- best positive scenario per symbol
- max plan count
- minimum net carry threshold
- planned notional for observation only

## Safety

Mission 53 is shadow-only planning.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All plan records preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Verdict

Mission 53 converts calibrated positive scenarios into shadow observation plans only.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
