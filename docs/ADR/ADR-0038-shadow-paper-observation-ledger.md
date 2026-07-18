# ADR-0038: Shadow Paper Observation Ledger

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

Mission 37 approved only shadow-paper observation.

DeltaGrid now needs a dedicated observation ledger to track approved shadow observations with auditability before any further automation is considered.

The system must remain safe and free.

## Decision

Add a shadow paper observation ledger.

Files:

- offchain/backtest/shadow_paper_observation_ledger.py
- offchain/tests/test_shadow_paper_observation_ledger.py

Code commit:

- 07743ad Add shadow paper observation ledger

The ledger reads:

- shadow_research_decision_gate_reports
- shadow_replay_performance_reports
- shadow_candidate_replay_scenarios

The ledger writes:

- shadow_paper_observation_ledger
- shadow_paper_observation_reports

The ledger tracks:

- observation id
- ledger label
- open time
- close time
- status
- mode
- symbol
- thesis
- simulated notional
- expected funding edge
- expected annualized funding
- risk snapshot
- decision gate reference
- performance report reference
- replay reference
- scenario reference
- live trading status
- live order status
- capital deployment status
- realized simulated outcome

## Safety

The ledger is shadow-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All observations must keep:

- live_trading = DISABLED
- live_order_sent = false
- capital_deployment = BLOCKED

## Mission 38 Verification

Expected verification:

- Mission 38 unit tests pass
- full offchain suite passes
- ledger opens approved shadow observations from Mission 37 gate
- ledger records two approved BTCUSDT shadow observations from Mission 35 replay
- observation report shows live_trading_breach_count = 0
- SQLite rows persist correctly

## Verdict

Mission 38 improves shadow-paper observability.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Continue shadow research infrastructure.
