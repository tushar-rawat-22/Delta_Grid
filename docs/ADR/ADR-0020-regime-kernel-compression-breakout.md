# ADR-0020: Regime Kernel and Compression Breakout Lab

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 18 showed weak walk-forward stability.

Mission 19 showed that stricter moving-average controls reduced drawdown but weakened returns and Sharpe.

Mission 20 introduces shared indicators, regime classification, and the first regime-aware institutional candidate lab.

---

## Decision

Add three components:

- Shared indicator engine
- Regime kernel
- Compression breakout lab

Files:

- offchain/backtest/indicator_engine.py
- offchain/tests/test_indicator_engine.py
- offchain/backtest/regime_kernel.py
- offchain/tests/test_regime_kernel.py
- offchain/backtest/compression_breakout_lab.py
- offchain/tests/test_compression_breakout_lab.py

Code commits:

- 7939c29 Add shared indicator engine
- df58279 Add regime kernel
- d8b0037 Add compression breakout lab

---

## Indicator Engine

Added reusable indicators:

- SMA
- EMA
- rolling standard deviation
- rolling percentile rank
- ATR
- RSI
- ADX
- Bollinger bandwidth
- Donchian channel
- simple returns
- rolling realized volatility

---

## Regime Kernel

Added regime classification:

- BULL_TREND
- BEAR_TREND
- SIDEWAYS
- COMPRESSION
- EXPANSION
- LOW_VOLATILITY
- HIGH_VOLATILITY
- PANIC_VOLATILITY
- MIXED_REGIME
- INSUFFICIENT_DATA

---

## Compression Breakout Lab

Strategy family:

- compression_breakout

Variants tested:

- donchian55_exit20_bb25_atr60_vol110_ema50
- donchian40_exit15_bb30_atr65_vol105_ema50
- donchian80_exit30_bb20_atr55_vol120_ema100

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

Variants tested:

- 3

Walk-forward splits:

- 5

Split results:

- 15

Summary results:

- 3

Approved variants:

- 0

Global verdict:

- REJECT_ALL_COMPRESSION_BREAKOUT_VARIANTS_NO_LIVE_TRADING

---

## Best Variant

Variant:

- compression_breakout donchian40_exit15_bb30_atr65_vol105_ema50

Splits tested:

- 5

GO splits:

- 0

Rejected splits:

- 5

Average net return:

- -0.396776545013587001489934869237738922756%

Average excess return:

- 0.371746881830666153902629573407595692088%

Worst drawdown:

- 1.983882725067935007449674346188694613780%

Average Sharpe:

- -0.5018140033361846611830239793745038497856

Average profit factor:

- 0

Total trades:

- 1

Compression signals:

- 113

Final verdict:

- NO_GO_STABILITY_FAILURE

Recommended action:

- REWORK_REGIME_FILTERS

---

## Investment Committee Verdict

Indicator engine:

- GO

Regime kernel:

- GO

Compression breakout framework:

- GO

Compression breakout variants:

- NO-GO

Live trading:

- NO-GO

Reason:

- approved_count is 0
- total trades are too low
- Sharpe is negative
- strategy failed walk-forward stability
- no variant is approved for live execution

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
