# ADR-0049: Real Market Public Data Ingestion

## Status

Accepted

## Context

Mission 48 approved only real-market alpha engine buildout and blocked live trading and capital deployment.

DeltaGrid now needs a public-data ingestion layer for real market information without API keys or trading permissions.

## Decision

Add a real market public data ingestion module.

Files:

- offchain/backtest/real_market_public_data_ingestion.py
- offchain/tests/test_real_market_public_data_ingestion.py

Code commit:

- f6703de Add real market public data ingestion

The module ingests Binance USDS-M Futures public data for:

- mark price
- index price
- basis bps
- latest funding rate
- funding history average
- 24h ticker quote volume
- bid/ask book-top spread

The module writes:

- real_market_public_data_snapshots
- real_market_public_data_reports

The module supports:

- online public API mode
- offline sample mode for deterministic tests
- online mode with sample fallback for local resilience

## Safety

Mission 49 is public-data-only.

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

Mission 49 starts the real-market alpha engine buildout under shadow-only constraints.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
