# ADR-0031: Paper Trading Engine

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 30 added a candidate ranking engine.

DeltaGrid now needs a paper-trading layer that converts ranked candidates into simulated positions, simulated trades, paper PnL, and equity-curve records.

This mission still does not execute real trades.

---

## Decision

Add paper trading engine.

Files:

- offchain/backtest/paper_trading_engine.py
- offchain/tests/test_paper_trading_engine.py

Code commit:

- 93bb586 Add paper trading engine

---

## Tables Added

- paper_trading_positions
- paper_trading_trades
- paper_trading_equity_curve
- paper_trading_summary

---

## Paper Trading Logic

The engine simulates:

- ranked candidate eligibility
- allocation sizing
- gross notional
- long spot / short perpetual structure
- expected funding accrual
- execution-cost drag
- simulated net PnL
- simulated return
- equity curve
- drawdown
- win rate
- profit factor
- GO / NO-GO paper-trading verdict

---

## Mission 31 Verification

Run label:

- mission_31_paper_trading_engine

Source ranking run:

- mission_30_candidate_ranking_engine

Latest run summary:

- summary=(18, 0, 0, 0, '10000', '10000', '0', '0', '0', '0', '0', 'NO_GO_NO_ELIGIBLE_PAPER_CANDIDATES', 'KEEP_SCANNING_AND_WAIT_FOR_RANKED_CANDIDATES') positions=[]

---

## Investment Committee Verdict

Paper trading engine:

- GO

Current paper candidates:

- depend on ranked candidates from Mission 30

Live trading:

- NO-GO

Reason:

- this is still paper-only
- no live execution
- no position sizing governor
- no capital allocation engine
- no exchange gateway
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
