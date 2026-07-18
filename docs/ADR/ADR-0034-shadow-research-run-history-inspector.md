# ADR-0034: Shadow Research Run History Inspector

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

Mission 33 added the unified free shadow research runner.

That runner can create shadow pipeline runs, stage results, alerts, and markdown reports.

DeltaGrid now needs a read-only way to inspect accumulated shadow research history before adding more automation.

The project must remain safe and free:

- no live trading
- no private keys
- no signing
- no paid APIs
- no real capital
- no cloud dependency

## Decision

Add a shadow research run history inspector.

Files:

- offchain/backtest/research_run_history_inspector.py
- offchain/tests/test_research_run_history_inspector.py

Code commit:

- 1937ebd Add shadow research run history inspector

The inspector reads Mission 33 SQLite tables:

- research_pipeline_runs
- research_pipeline_stage_results
- research_pipeline_reports

It summarizes:

- total runs
- verdict counts
- latest run
- latest verdict
- alerts
- blocking alerts
- stage counts
- report lengths
- live trading safety flags

## Safety

The inspector is read-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses real capital

Live trading must remain:

- DISABLED

## Mission 34 Verification

Verification commands:

- python -m pytest offchain/tests/test_research_run_history_inspector.py -q
- python -m pytest offchain/tests -q
- python -m offchain.backtest.research_run_history_inspector --limit 5

Expected safety result:

- live_trading_disabled_all: true
- breach_count: 0

## Verdict

Mission 34 adds observability only.

Live trading remains:

- NO-GO

Next valid phase:

- Continue shadow research infrastructure.
