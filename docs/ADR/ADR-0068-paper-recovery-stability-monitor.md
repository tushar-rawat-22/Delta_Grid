# ADR-0068: Paper Recovery Stability Monitor

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

Mission 67 armed a paper-only drawdown kill switch.

DeltaGrid needs a recovery stability layer that confirms whether paper observation remains stable after the kill switch is armed.

## Decision

Add the Paper Recovery Stability Monitor.

Files:

- offchain/recovery/__init__.py
- offchain/recovery/paper_recovery_stability_monitor.py
- offchain/tests/test_paper_recovery_stability_monitor.py

Code commit:

- e25afdc Add paper recovery stability monitor

The monitor reads:

- paper_drawdown_kill_switch_reviews
- paper_drawdown_kill_switch_checks
- paper_drawdown_kill_switch_events
- paper_observation_performance_runs
- paper_observation_position_snapshots

The monitor writes:

- paper_recovery_stability_reviews
- paper_recovery_stability_checks
- paper_recovery_stability_events
- paper_recovery_stability_reports

## Safety

Mission 68 is paper recovery analytics only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

## Consequence

DeltaGrid can now confirm stable paper observation after the paper drawdown kill switch is armed.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
