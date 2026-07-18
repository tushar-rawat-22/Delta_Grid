# ADR-0035: Shadow Candidate Replay Harness

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

Mission 34 added a read-only history inspector for shadow research runs.

DeltaGrid now needs repeatable shadow scenarios that can generate controlled research history without using live data, paid APIs, private keys, signing, or real capital.

## Decision

Add a shadow candidate replay harness.

Files:

- offchain/backtest/shadow_candidate_replay_harness.py
- offchain/tests/test_shadow_candidate_replay_harness.py

Code commit:

- 9b09f52 Add shadow candidate replay harness

The harness generates deterministic replay scenarios:

- fail_closed_baseline
- approved_shadow_btc
- mixed_shadow_set
- non_universe_rejection

The harness writes replay metadata into SQLite tables:

- shadow_candidate_replay_runs
- shadow_candidate_replay_scenarios

## Safety

The harness only calls the Mission 33 shadow research runner.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

Live trading remains:

- DISABLED

## Mission 35 Verification

Expected verification:

- Mission 35 unit tests pass
- full offchain suite passes
- replay harness creates four controlled scenarios
- replay history shows live_trading_breach_count = 0
- research history inspector shows live_trading_disabled_all = true

## Verdict

Mission 35 improves repeatable research simulation.

Live trading remains:

- NO-GO

Next valid phase:

- Continue shadow research infrastructure.
