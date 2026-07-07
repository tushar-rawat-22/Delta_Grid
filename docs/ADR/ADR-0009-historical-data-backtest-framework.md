# ADR-0009: Historical Data and Backtest Framework

## Status

Accepted

## Date

2026-07-07

---

## Context

DeltaGrid is now being treated as a serious trading research system.

Before any strategy can be trusted, it must be tested historically with:

- fees
- slippage
- drawdown
- Sharpe ratio
- profit factor
- win rate
- trade count

Mission 9 adds the foundation for this.

---

## Decision

Add historical data and backtest framework.

Files created or changed:

- offchain/db/schema.py
- offchain/backtest/__init__.py
- offchain/backtest/historical_data.py
- offchain/backtest/metrics.py
- offchain/backtest/backtest_engine.py
- offchain/tests/test_backtest_framework.py

Commit:

- 7b863f5 Add historical data and backtest framework

---

## Tables Added

- historical_candles
- backtest_runs
- backtest_trades

---

## Baseline Strategy Tested

Strategy:

- ma_crossover_baseline

Version:

- v1

Symbol:

- WETH_USDC_DEMO

Status:

- research_only

---

## Backtest Result

Net return:

- -42.47%

Max drawdown:

- 55.30%

Sharpe ratio:

- -1.44

Profit factor:

- 0.42

Win rate:

- 29.41%

Trades:

- 17

---

## Recommendation

Framework:

- GO

MA crossover strategy:

- NO-GO

Reason:

- negative return
- high drawdown
- negative Sharpe
- weak profit factor
- low win rate
- insufficient confidence for live use

---

## Safety Status

Still safe:

- no private keys
- no signing
- no real trades
- no real capital
- research backtest only
