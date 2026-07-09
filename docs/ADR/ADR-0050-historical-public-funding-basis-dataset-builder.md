# ADR-0050: Historical Public Funding and Basis Dataset Builder

## Status

Accepted

## Context

Mission 49 proved that DeltaGrid can ingest live Binance USDS-M Futures public data online without fallback.

DeltaGrid now needs historical public funding records and latest basis observations so the alpha engine can evaluate funding persistence, basis conditions, spread cost, and symbol-level dataset quality.

## Decision

Add a historical public funding and basis dataset builder.

Files:

- offchain/backtest/historical_public_funding_basis_dataset_builder.py
- offchain/tests/test_historical_public_funding_basis_dataset_builder.py

Code commit:

- 1ea549f Add historical public funding and basis dataset builder

The builder writes:

- historical_public_funding_rates
- historical_public_basis_observations
- historical_public_funding_basis_dataset_reports

The builder supports:

- online public API funding history
- latest basis observations from Mission 49 snapshots
- deterministic offline sample mode
- online failure sample fallback mode
- dataset quality reports

## Safety

Mission 50 is public-data-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All records preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Verdict

Mission 50 creates the first historical alpha dataset.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
