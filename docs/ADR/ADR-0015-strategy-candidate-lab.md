# ADR-0015: Strategy Candidate Lab

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 14 added strategy validation.

Mission 15 expands the system from one strategy to multiple strategy candidates.

The goal is to compare different strategies against buy-and-hold and reject weak candidates.

---

## Decision

Add strategy candidate lab.

Files:

- offchain/backtest/strategy_candidate_lab.py
- offchain/tests/test_strategy_candidate_lab.py

Commit:

- f7b06b9 Add strategy candidate lab

---

## Strategies Tested

Candidate strategies:

- ma_crossover fast_10_slow_30
- ma_crossover fast_20_slow_60
- momentum lookback_20_threshold_300_hold_10
- breakout window_20
- mean_reversion window_20_deviation_500

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

Candles seen:

- 1277

Run label:

- mission_15_candidate_lab

Candidates tested:

- 5

Approved:

- 0

Rejected or insufficient:

- 5

Global verdict:

- REJECT_ALL_NO_LIVE_TRADING

---

## Best Candidate

Strategy:

- ma_crossover

Version:

- fast_20_slow_60

Net return:

- 96.21182590124005928320132057408734590970%

Benchmark return:

- 30.4409176548347894909482898674384240500%

Excess return:

- 65.77090824640526979225303070664892185970%

Max drawdown:

- 40.90738899223450848223904999801972024854%

Sharpe ratio:

- 0.6767132355315847

Profit factor:

- 2.145469759090933450561693116786933058608

Trades:

- 12

Verdict:

- NO_GO_DRAWDOWN_TOO_HIGH

---

## Ranked Candidate Verdicts

1. ma_crossover fast_20_slow_60

- verdict: NO_GO_DRAWDOWN_TOO_HIGH

2. mean_reversion window_20_deviation_500

- verdict: NO_GO_DRAWDOWN_TOO_HIGH

3. ma_crossover fast_10_slow_30

- verdict: NO_GO_DRAWDOWN_TOO_HIGH

4. breakout window_20

- verdict: NO_GO_UNDERPERFORMS_BENCHMARK

5. momentum lookback_20_threshold_300_hold_10

- verdict: NO_GO_UNDERPERFORMS_BENCHMARK

---

## Investment Committee Verdict

Strategy candidate lab:

- GO

Best candidate:

- WATCHLIST_ONLY

Live trading:

- NO-GO

Reason:

- no candidate passed all rules
- best candidate exceeded drawdown limit
- approved_count is 0
- global verdict is REJECT_ALL_NO_LIVE_TRADING

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
