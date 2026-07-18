# ADR-0067: Paper Drawdown Kill Switch

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

Mission 66 added paper observation performance monitoring.

DeltaGrid now needs a hard paper-only kill switch that can arm during healthy observation and trigger when drawdown, position loss, fee drag, alert, or safety limits fail.

## Decision

Add the Paper Drawdown Kill Switch.

Files:

- offchain/safety/__init__.py
- offchain/safety/paper_drawdown_kill_switch.py
- offchain/tests/test_paper_drawdown_kill_switch.py

Code commit:

- e733e19 Add paper drawdown kill switch

The kill switch reads:

- paper_observation_performance_runs
- paper_observation_position_snapshots
- paper_observation_performance_alerts

The kill switch writes:

- paper_drawdown_kill_switch_reviews
- paper_drawdown_kill_switch_checks
- paper_drawdown_kill_switch_events
- paper_drawdown_kill_switch_reports

## Safety

Mission 67 is paper risk control only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

## Consequence

DeltaGrid can now stop paper observation continuation when paper drawdown thresholds fail.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
