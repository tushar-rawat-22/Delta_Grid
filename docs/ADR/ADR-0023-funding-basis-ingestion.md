# ADR-0023: Funding / Basis Ingestion

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 22 added the funding / basis data model.

Mission 23 moves from synthetic demo rows to public exchange market-data ingestion.

This mission still does not execute trades.

It only ingests public data for research.

---

## Decision

Add Binance USD-M public data ingestion for funding / basis research.

Files:

- offchain/backtest/funding_basis_ingestion.py
- offchain/tests/test_funding_basis_ingestion.py

Code commit:

- 266f90d Add funding basis ingestion

---

## Public Data Ingested

Sources:

- Binance Futures funding history
- Binance Futures mark price / premium index
- Binance Futures open interest

Tables written:

- funding_rates
- perp_mark_prices
- spot_perp_basis_snapshots
- delta_neutral_research_candidates
- funding_basis_ingestion_runs

---

## Mission 23 Verification

Run label:

- mission_23_funding_basis_ingestion

Latest run summary:

- 20|1|1|1|0.00002844|3.11418000|-0.03464239274341806018053250034036187713858|3.11418000|NO_GO_LOW_FUNDING|OK

Global verdict:

- REAL_INGESTION_READY_NO_LIVE_TRADING

---

## Investment Committee Verdict

Funding / basis ingestion:

- GO

Delta-neutral strategy:

- NOT YET TESTED

Live trading:

- NO-GO

Reason:

- public data ingestion exists
- no backtest engine yet
- no liquidation model
- no borrow-cost model
- no execution-cost model
- no exchange-risk model
- no private keys
- no real trades

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
