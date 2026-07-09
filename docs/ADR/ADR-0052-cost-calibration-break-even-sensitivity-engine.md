# ADR-0052: Cost Calibration and Break-Even Sensitivity Engine

## Status

Accepted

## Context

Mission 51 produced no approved alpha candidates. BTC and ETH were watchlist-only because cost-adjusted carry was negative. SOL was rejected because funding direction was unstable.

DeltaGrid now needs to know whether the funding/basis strategy is structurally bad or whether it becomes viable under lower cost, tighter slippage, or longer holding periods.

## Decision

Add a cost calibration and break-even sensitivity engine.

Files:

- offchain/backtest/cost_calibration_break_even_sensitivity_engine.py
- offchain/tests/test_cost_calibration_break_even_sensitivity_engine.py

Code commit:

- 0ea72bd Add cost calibration break-even sensitivity engine

The engine reads:

- funding_basis_alpha_candidates
- funding_basis_alpha_scanner_reports

The engine writes:

- cost_calibration_break_even_scenarios
- cost_calibration_break_even_reports

The engine evaluates grids for:

- fee bps per side
- slippage bps
- holding funding events

The engine computes:

- gross horizon carry bps
- estimated cost bps
- net carry bps
- break-even funding bps
- funding gap to break-even
- positive scenario counts
- symbol viability under low-cost or longer-horizon assumptions

## Safety

Mission 52 is shadow-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All calibration records preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Verdict

Mission 52 determines whether rejected/watchlist candidates can become positive under lower-cost or longer-horizon assumptions.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
