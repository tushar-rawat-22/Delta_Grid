# ADR-0026: Funding Strategy Walk-Forward Validation

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

Mission 25 added a delta-neutral funding backtest engine.

Mission 26 validates funding strategy stability across walk-forward splits and parameter variants.

This mission still does not execute trades.

---

## Decision

Add funding walk-forward validation.

Files:

- offchain/backtest/funding_walk_forward_validation.py
- offchain/tests/test_funding_walk_forward_validation.py

Code commit:

- b929c20 Add funding walk forward validation

---

## Tables Added

- funding_walk_forward_split_results
- funding_walk_forward_summary

---

## Validation Logic

The validator tests:

- train/test split windows
- multiple funding threshold variants
- split-level net return
- split-level trade count
- split-level profit factor
- split-level drawdown
- split-level GO / NO-GO verdict
- summary-level stability score
- summary-level final verdict

---

## Mission 26 Verification

Run label:

- mission_26_funding_walk_forward_validation

Source run:

- mission_23_funding_basis_ingestion

Latest run summary:

- loose_entry5_exit2_hold20_cost20|2|0|2|2|-0.17630900000000000000000000000000000000|-0.35261800000000000000000000000000000000|0.18350200000000000000000000000000000000|0|5.51507700|NO_GO_WALK_FORWARD_STABILITY|REWORK_FUNDING_ENTRY_EXIT_RULES || balanced_entry8_exit4_hold20_cost20|2|0|2|2|-0.18456750000000000000000000000000000000|-0.36913500000000000000000000000000000000|0.18910900000000000000000000000000000000|0|5.51507700|NO_GO_WALK_FORWARD_STABILITY|REWORK_FUNDING_ENTRY_EXIT_RULES || strict_entry10_exit5_hold20_cost20|2|0|2|0|0|0|0|0|5.51507700|INSUFFICIENT_TOTAL_TRADES|BROADEN_SAMPLE_OR_LOWER_THRESHOLDS

---

## Investment Committee Verdict

Funding walk-forward validation:

- GO

Current variants:

- verdict depends on latest real funding path

Live trading:

- NO-GO

Reason:

- this is still research-only
- no liquidation model
- no leverage model
- no exchange-risk model
- no position sizing engine
- no risk governor
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
