# ADR-0014: Strategy Validation Engine

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

Mission 13 added real ETHUSDT historical data.

Mission 14 adds stricter strategy validation.

A strategy must now beat benchmark logic and survive walk-forward testing before it can be considered research-worthy.

---

## Decision

Add strategy validation engine.

Files:

- offchain/backtest/strategy_validation.py
- offchain/tests/test_strategy_validation.py

Commit:

- 47ac51b Add strategy validation engine

---

## Validation Added

The engine validates:

- MA crossover strategy
- buy-and-hold benchmark
- excess return
- max drawdown
- Sharpe ratio
- profit factor
- walk-forward splits
- final strategy verdict

---

## Real ETHUSDT Result

Symbol:

- ETHUSDT

Timeframe:

- 1d

Source:

- binance_spot

Candles seen:

- 1277

---

## Full-Period Result

Strategy:

- ma_crossover_baseline

Version:

- fast_10_slow_30

Net return:

- 30.77660443634719226696698669200061823290%

Benchmark return:

- 30.4409176548347894909482898674384240500%

Excess return:

- 0.33568678151240277601869682456219418290%

Max drawdown:

- 44.94790673961142022789518187436905641133%

Sharpe ratio:

- 0.3884730994437054

Profit factor:

- 1.187448392982318393539929719842272549569

Trades:

- 24

Verdict:

- NO_GO_DRAWDOWN_TOO_HIGH

---

## Walk-Forward Result

Splits:

- 5

GO_FOR_RESEARCH:

- 0

Rejected or insufficient:

- 5

Split verdicts:

- split 0: INSUFFICIENT_SAMPLE
- split 1: NO_GO_UNDERPERFORMS_BENCHMARK
- split 2: INSUFFICIENT_SAMPLE
- split 3: NO_GO_UNDERPERFORMS_BENCHMARK
- split 4: NO_GO_WEAK_SHARPE

---

## Investment Committee Verdict

Strategy validation framework:

- GO

MA crossover strategy:

- NO-GO

Live trading:

- NO-GO

Reason:

- drawdown is too high
- excess return over buy-and-hold is too small
- walk-forward validation failed
- 0 out of 5 splits passed

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
