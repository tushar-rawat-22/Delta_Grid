# ADR-0039: Shadow Observation Lifecycle Manager

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

Mission 38 created a shadow-paper observation ledger.

DeltaGrid now needs lifecycle tracking for open shadow observations before outcomes can be analyzed or any future automation can be considered.

The system must remain safe and free.

## Decision

Add a shadow observation lifecycle manager.

Files:

- offchain/backtest/shadow_observation_lifecycle_manager.py
- offchain/tests/test_shadow_observation_lifecycle_manager.py

Code commit:

- 8669899 Add shadow observation lifecycle manager

The lifecycle manager reads:

- shadow_paper_observation_ledger

The lifecycle manager writes:

- shadow_observation_lifecycle_snapshots
- shadow_observation_lifecycle_reports

It evaluates:

- observation age
- holding period
- expected funding accrual
- expected funding return
- liquidation buffer
- spread
- slippage
- liquidity score
- risk flags
- close eligibility
- safety breach status

## Safety

The lifecycle manager is shadow-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All lifecycle snapshots must preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Mission 39 Verification

Expected verification:

- Mission 39 unit tests pass
- full offchain suite passes
- lifecycle manager tracks open Mission 38 observations
- lifecycle report shows no live trading breach
- lifecycle snapshots persist in SQLite

## Verdict

Mission 39 improves shadow observation tracking.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Continue shadow research infrastructure.
