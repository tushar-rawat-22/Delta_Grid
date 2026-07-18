# ADR-0021: Volatility-Targeted Time-Series Momentum Lab

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

Mission 18 found weak walk-forward stability.

Mission 19 showed controlled moving-average strategies reduced drawdown but weakened returns and Sharpe.

Mission 20 added the shared indicator engine, regime kernel, and compression breakout lab.

Mission 21 adds an institutional time-series momentum candidate using volatility targeting and regime filters.

---

## Decision

Add volatility-targeted time-series momentum lab.

Files:

- offchain/backtest/vt_tsmom_lab.py
- offchain/tests/test_vt_tsmom_lab.py

Code commit:

- 8258dbf Add volatility targeted TSMOM lab

---

## Strategy Family

Strategy:

- vt_tsmom

Core logic:

- multi-horizon momentum
- EMA trend filter
- ADX trend confirmation
- ATR stop
- ATR trailing exit
- volatility-targeted position sizing
- regime-aware rejection filters
- cooldown after exit

Variants tested:

- lb21_63_126_ema200_adx18_vol25_atr3
- lb14_42_84_ema150_adx20_vol20_atr25
- lb30_90_180_ema200_adx18_vol30_atr35

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

- REJECT_ALL_VT_TSMOM_VARIANTS_NO_LIVE_TRADING

---

## Best Variant

Variant:

- vt_tsmom lb21_63_126_ema200_adx18_vol25_atr3

Splits tested:

- 5

GO splits:

- 0

Rejected splits:

- 5

Average net return:

- 0%

Average excess return:

- 0.768523426844253155392564442645334614844%

Worst drawdown:

- 0%

Average Sharpe:

- 0

Average profit factor:

- 0

Total trades:

- 0

Momentum signals:

- 0

Final verdict:

- NO_GO_STABILITY_FAILURE

Recommended action:

- REWORK_MOMENTUM_REGIME_FILTERS

---

## Split Verdict Finding

All VT-TSMOM split verdicts were:

- INSUFFICIENT_TRADES

This means the strategy framework works, but the current filters are too restrictive for ETHUSDT 1d.

---

## Investment Committee Verdict

VT-TSMOM framework:

- GO

VT-TSMOM variants:

- NO-GO

Live trading:

- NO-GO

Reason:

- approved_count is 0
- all variants failed stability
- all split verdicts were INSUFFICIENT_TRADES
- total trades were too low
- no candidate is approved for live execution

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
