# ADR-0022: Funding / Basis Data Model

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

## Date

2026-07-08

---

## Context

Mission 21 completed the volatility-targeted time-series momentum lab.

The next research direction is a crypto-native structural edge:

- perpetual funding
- spot/perp basis
- delta-neutral candidate evaluation

This mission does not execute trades.

It only prepares the data model.

---

## Decision

Add funding / basis data model.

Files:

- offchain/backtest/funding_basis_model.py
- offchain/tests/test_funding_basis_model.py

Code commit:

- 40c7ae2 Add funding basis data model

---

## Tables Added

- funding_rates
- perp_mark_prices
- spot_perp_basis_snapshots
- delta_neutral_research_candidates

---

## Capabilities Added

- funding-rate annualization
- spot/perp basis calculation
- funding-rate upsert
- perp mark price upsert
- basis snapshot storage
- delta-neutral candidate evaluation
- research-only demo seed

---

## Mission 22 Demo Verification

Demo symbol:

- ETHUSDT

Spot exchange:

- Binance Spot

Perp exchange:

- Binance Futures

Demo funding rate:

- 0.0002 per 8h

Annualized funding rate:

- 21.9000%

Demo spot price:

- 3100

Demo perp mark price:

- 3106.20

Demo basis:

- 0.200%

Global verdict:

- DATA_MODEL_READY_NO_LIVE_TRADING

---

## Investment Committee Verdict

Funding / basis data model:

- GO

Delta-neutral strategy:

- NOT YET TESTED

Live trading:

- NO-GO

Reason:

- only data model exists
- no real exchange data ingestion yet
- no order execution
- no risk governor
- no liquidation model

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
