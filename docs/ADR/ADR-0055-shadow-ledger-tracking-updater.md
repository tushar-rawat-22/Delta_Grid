# ADR-0055: Shadow Ledger Tracking Updater

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

Mission 54 created formal shadow ledger entries for BTCUSDT and ETHUSDT. The entries start in shadow tracking mode and require periodic public-data updates.

DeltaGrid now needs a tracking updater that recalculates expected remaining carry and validates whether the observation should remain active.

## Decision

Add a shadow ledger tracking updater.

Files:

- offchain/backtest/shadow_ledger_tracking_updater.py
- offchain/tests/test_shadow_ledger_tracking_updater.py

Code commit:

- 7af57c4 Add shadow ledger tracking updater

The updater reads:

- shadow_observation_ledger_entries
- historical_public_funding_rates
- historical_public_basis_observations

The updater writes:

- shadow_ledger_tracking_updates
- shadow_ledger_tracking_update_reports

The updater computes:

- latest funding bps
- latest basis bps
- latest spread bps
- remaining funding events
- updated expected remaining carry bps
- carry drift bps
- observation state after update

## Safety

Mission 55 is shadow-only tracking.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All tracking records preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Verdict

Mission 55 starts active shadow tracking for formal ledger entries.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
