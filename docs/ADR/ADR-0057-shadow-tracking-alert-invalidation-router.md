# ADR-0057: Shadow Tracking Alert and Invalidation Router

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

Mission 56 summarized BTCUSDT and ETHUSDT shadow tracking performance. Both symbols were strong, active, and safe.

DeltaGrid now needs an alert and invalidation router that converts performance reports into explicit route decisions.

## Decision

Add a shadow tracking alert and invalidation router.

Files:

- offchain/backtest/shadow_tracking_alert_invalidation_router.py
- offchain/tests/test_shadow_tracking_alert_invalidation_router.py

Code commit:

- 37bb975 Add shadow tracking alert invalidation router

The router reads:

- shadow_tracking_performance_reports

The router writes:

- shadow_tracking_alert_routes
- shadow_tracking_alert_router_reports

The router creates route decisions for:

- continue shadow tracking
- warning / tighter monitoring
- invalidate shadow observation
- refresh public data
- safety block

## Safety

Mission 57 is shadow-only routing.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All alert route records preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Verdict

Mission 57 adds explicit alert routing and invalidation decisions for shadow tracking.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
