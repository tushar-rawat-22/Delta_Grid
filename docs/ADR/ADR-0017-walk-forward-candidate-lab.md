# ADR-0017: Walk-Forward Candidate Lab

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 15 tested multiple strategy candidates.

Mission 16 added drawdown controls.

Mission 17 tests whether those candidates survive walk-forward validation.

A strategy that only works on full-period data must be rejected.

---

## Decision

Add walk-forward candidate lab.

Files:

- offchain/backtest/walk_forward_candidate_lab.py
- offchain/tests/test_walk_forward_candidate_lab.py

Commit:

- 0ef95c8 Add walk-forward candidate lab

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

Candidates tested:

- 7

Walk-forward splits:

- 5

Split results:

- 35

Summary results:

- 7

Approved candidates:

- 0

Global verdict:

- REJECT_ALL_NO_LIVE_TRADING

---

## Best Candidate

Candidate:

- ma_crossover fast_20_slow_60

Splits tested:

- 5

GO splits:

- 0

Rejected splits:

- 5

Average net return:

- 2.545765355319971815276376712479456507926%

Average excess return:

- 3.31428878216422497066894115512479112277%

Worst drawdown:

- 33.40152279173245015518082401738193045617%

Average Sharpe:

- 0.21214942410672526

Total trades:

- 7

Final verdict:

- NO_GO_WALK_FORWARD_FAILURE

---

## Investment Committee Verdict

Walk-forward framework:

- GO

Strategy candidates:

- NO-GO

Live trading:

- NO-GO

Reason:

- no candidate passed walk-forward validation
- best candidate had 0 GO splits
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
