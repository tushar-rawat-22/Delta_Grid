# ADR-0016: Drawdown Control Lab

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

Mission 15 found a high-return candidate.

Best Mission 15 candidate:

- ma_crossover fast_20_slow_60

Problem:

- return was strong
- drawdown was too high
- live trading remained NO-GO

Mission 16 tests drawdown control filters.

---

## Decision

Add drawdown control lab.

Files:

- offchain/backtest/drawdown_control_lab.py
- offchain/tests/test_drawdown_control_lab.py

Commit:

- a74134e Add drawdown control lab

---

## Controls Tested

Controls added:

- stop-loss
- trailing stop
- volatility filter
- drawdown guard
- cooldown after drawdown breach

Base strategy:

- controlled_ma fast_20_slow_60

Benchmark:

- buy-and-hold

---

## Real ETHUSDT Test

Symbol:

- ETHUSDT

Timeframe:

- 1d

Source:

- binance_spot

Run label:

- mission_16_drawdown_control_lab

Candidates tested:

- 5

Approved:

- 0

Rejected:

- 5

Global verdict:

- REJECT_ALL_NO_LIVE_TRADING

---

## Best Candidate

Strategy:

- controlled_ma

Version:

- fast_20_slow_60_stop_12

Net return:

- 113.8743488169851381696565986752932650320%

Benchmark return:

- 30.4409176548347894909482898674384240500%

Excess return:

- 83.4334311621503486787083088078548409820%

Max drawdown:

- 41.87455183371898312191756397825277109708%

Sharpe ratio:

- 0.7401939708173589

Profit factor:

- 2.672148520415210068522801211221636535987

Trades:

- 14

Verdict:

- NO_GO_DRAWDOWN_TOO_HIGH

---

## Important Finding

One candidate reduced drawdown below 30%.

Candidate:

- fast_20_slow_60_stop_10_trail_15_maxvol_85_ddguard_25_cooldown_20

Result:

- max drawdown: 26.69291884830347618814910813002149397686%
- net return: 20.97398465592231407372609072731493339820%
- benchmark return: 30.4409176548347894909482898674384240500%

Verdict:

- NO_GO_UNDERPERFORMS_BENCHMARK

Meaning:

- drawdown control worked
- return became too weak

---

## Investment Committee Verdict

Drawdown control framework:

- GO

Best candidate:

- WATCHLIST_ONLY

Live trading:

- NO-GO

Reason:

- no candidate passed all rules
- best return candidate still had drawdown above 30%
- lowest drawdown candidate underperformed benchmark
- approved_count is 0

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
