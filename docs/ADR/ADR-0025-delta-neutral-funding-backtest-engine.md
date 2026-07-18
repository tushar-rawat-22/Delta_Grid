# ADR-0025: Delta-Neutral Funding Backtest Engine

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

Mission 22 added the funding / basis data model.

Mission 23 added public Binance funding / basis ingestion.

Mission 24 added the delta-neutral funding strategy lab.

Mission 25 turns the scoring layer into a research-only backtest engine.

This mission still does not execute trades.

---

## Decision

Add delta-neutral funding backtest engine.

Files:

- offchain/backtest/delta_neutral_funding_backtest.py
- offchain/tests/test_delta_neutral_funding_backtest.py

Code commit:

- 0792bc8 Add delta neutral funding backtest engine

---

## Tables Added

- delta_neutral_funding_backtest_trades
- delta_neutral_funding_backtest_results
- delta_neutral_funding_backtest_summary

---

## Backtest Logic

The engine simulates:

- long spot
- short perpetual
- funding carry collection
- basis entry / exit impact
- execution cost
- entry funding threshold
- exit funding threshold
- basis range filter
- max holding windows
- net return
- drawdown
- profit factor
- win rate
- GO / NO-GO verdict

---

## Mission 25 Verification

Run label:

- mission_25_delta_neutral_funding_backtest

Source run:

- mission_23_funding_basis_ingestion

Latest run summary:

- 20|1|-0.09745100000000000000000000000000000000|0.10254900|0.00000000000000000000000000000000000000000|0.2|0|0.09745100000000000000000000000000000000|0|6.46707000|1.66330500|10.95000000|NO_GO_LOW_AVG_FUNDING|WAIT_FOR_HIGHER_AVERAGE_FUNDING

Observed result:

- one trade created
- trade exited because funding dropped below exit threshold
- current ETHUSDT candidate rejected because average funding was too low

---

## Investment Committee Verdict

Delta-neutral funding backtest engine:

- GO

Current ETHUSDT backtest candidate:

- NO-GO

Live trading:

- NO-GO

Reason:

- current funding path is weak
- no liquidation model
- no leverage model
- no exchange failure model
- no real order book execution
- no position sizing engine
- no risk governor
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
