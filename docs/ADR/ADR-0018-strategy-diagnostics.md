# ADR-0018: Strategy Diagnostics and Failure Attribution

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

Mission 17 rejected all walk-forward strategy candidates.

Mission 18 identifies why each strategy failed.

The diagnostic layer must explain failure causes before any new strategy work.

---

## Decision

Add strategy diagnostics.

Files:

- offchain/backtest/strategy_diagnostics.py
- offchain/tests/test_strategy_diagnostics.py

Code commit:

- fd38244 Add strategy diagnostics

---

## Real ETHUSDT Diagnostic Result

Symbol:

- ETHUSDT

Timeframe:

- 1d

Source:

- binance_spot

Source run:

- mission_17_walk_forward_candidate_lab

Diagnostic run:

- mission_18_strategy_diagnostics

Candidates diagnosed:

- 7

Global verdict:

- DIAGNOSE_ONLY_NO_LIVE_TRADING

Primary failure across all candidates:

- WEAK_WALK_FORWARD_STABILITY

Failure counts:

- WEAK_WALK_FORWARD_STABILITY: 7

---

## Highest Severity Candidate

Candidate:

- ma_crossover fast_20_slow_60

Primary failure:

- WEAK_WALK_FORWARD_STABILITY

Severity score:

- 165

Recommended action:

- REWORK_FOR_STABILITY

---

## Investment Committee Verdict

Diagnostics framework:

- GO

Strategy candidates:

- NO-GO

Live trading:

- NO-GO

Reason:

- all candidates failed walk-forward stability
- no candidate is approved
- diagnostic output is research-only

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
