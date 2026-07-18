# ADR-0076: AI Label Quality and Leakage Guard

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

## Context

Mission 75 finalized paper-only outcome labels and marked them as offline-evaluation candidates while keeping training locked.

DeltaGrid needs a label quality and leakage guard before offline evaluation can consume finalized labels.

## Decision

Add the AI Label Quality and Leakage Guard.

Files:

- offchain/ai_dataset/label_quality_leakage_guard.py
- offchain/tests/test_label_quality_leakage_guard.py

Code commit:

- 1adadce Add AI label quality leakage guard

The guard reads:

- ai_paper_outcome_collection_runs
- ai_paper_outcome_collection_records
- ai_paper_outcome_final_labels
- ai_paper_outcome_collection_checks

The guard writes:

- ai_label_quality_leakage_guard_reviews
- ai_label_quality_leakage_guard_checks
- ai_label_quality_leakage_guard_findings
- ai_label_quality_leakage_guard_reports

## Safety

Mission 76 does not train a model.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
- performs autonomous strategy reweighting
- runs autonomous execution

Training remains locked.

## Consequence

DeltaGrid can now validate finalized labels for quality and leakage before offline evaluation.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Model training remains:

- NO-GO

Autonomous trading remains:

- NO-GO
