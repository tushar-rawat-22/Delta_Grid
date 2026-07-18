# ADR-0019: Stability Rework Lab

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

Mission 18 showed that all strategy candidates failed because of weak walk-forward stability.

Mission 19 attempts to rework stability using stricter controlled MA variants.

---

## Decision

Add stability rework lab.

Files:

- offchain/backtest/stability_rework_lab.py
- offchain/tests/test_stability_rework_lab.py

Code commit:

- f93a531 Add stability rework lab

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

- 5

Walk-forward splits:

- 5

Split results:

- 25

Summary results:

- 5

Approved variants:

- 0

Global verdict:

- REJECT_ALL_STABILITY_VARIANTS_NO_LIVE_TRADING

---

## Best Variant

Variant:

- stability_controlled_ma fast_20_slow_100_stop_8_trail_12_vol55_dd20_cd20

Splits tested:

- 5

GO splits:

- 0

Rejected splits:

- 5

Average net return:

- -3.38229550402847490908839551715134794650%

Average excess return:

- -2.613772077184221753695831074506013331656%

Worst drawdown:

- 17.64410096101552019914854246458599166621%

Average Sharpe:

- -0.44821659945187352

Total trades:

- 7

Final verdict:

- NO_GO_STABILITY_FAILURE

Recommended action:

- REWORK_STABILITY_FILTERS

---

## Investment Committee Verdict

Stability rework framework:

- GO

Strategy variants:

- NO-GO

Live trading:

- NO-GO

Reason:

- no stability variant passed
- best variant reduced drawdown but produced negative return
- approved_count is 0
- global verdict is REJECT_ALL_STABILITY_VARIANTS_NO_LIVE_TRADING

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
