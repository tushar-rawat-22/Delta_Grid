# ADR-0036: Shadow Replay Performance Reporter

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

Mission 35 added deterministic replay scenarios for shadow candidate research.

DeltaGrid can now create replay history, but it needs a compact performance-style report that summarizes approvals, rejections, paper positions, safety breaches, scenario distribution, and verdict counts.

The system must remain safe and free.

## Decision

Add a shadow replay performance reporter.

Files:

- offchain/backtest/shadow_replay_performance_reporter.py
- offchain/tests/test_shadow_replay_performance_reporter.py

Code commit:

- 36cb1fd Add shadow replay performance reporter

The reporter reads Mission 35 SQLite tables:

- shadow_candidate_replay_runs
- shadow_candidate_replay_scenarios

The reporter writes:

- shadow_replay_performance_reports

It summarizes:

- replay count
- scenario count
- pipeline run count
- total approved candidates
- total rejected candidates
- total shadow paper positions
- approval rate
- rejection rate
- paper position rate
- live trading breach count
- scenario distribution
- scenario verdict counts
- global verdict
- recommended action
- markdown report

## Safety

The reporter never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

Live trading remains:

- DISABLED

## Mission 36 Verification

Expected verification:

- Mission 36 unit tests pass
- full offchain suite passes
- performance report summarizes mission35-final-check
- live_trading_breach_count = 0
- markdown report is generated
- performance report row persists in SQLite

## Verdict

Mission 36 improves research reporting.

Live trading remains:

- NO-GO

Next valid phase:

- Continue shadow research infrastructure.
