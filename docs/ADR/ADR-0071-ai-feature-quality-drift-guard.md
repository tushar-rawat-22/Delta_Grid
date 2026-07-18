# ADR-0071: AI Feature Quality and Drift Guard

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

Mission 70 introduced a local deterministic AI paper-outcome learning engine that produces features, labels, and recommendation-only outputs.

DeltaGrid needs a feature-quality and drift guard before AI dataset expansion continues.

## Decision

Add the AI Feature Quality and Drift Guard.

Files:

- offchain/ai_quality/__init__.py
- offchain/ai_quality/feature_quality_drift_guard.py
- offchain/tests/test_feature_quality_drift_guard.py

Code commit:

- 7a7761b Add AI feature quality drift guard

The guard reads:

- ai_paper_outcome_learning_runs
- ai_paper_outcome_learning_features
- ai_paper_outcome_learning_labels
- ai_paper_outcome_learning_recommendations

The guard writes:

- ai_feature_quality_drift_guard_reviews
- ai_feature_quality_drift_guard_checks
- ai_feature_quality_drift_guard_feature_drifts
- ai_feature_quality_drift_guard_reports

## Safety

Mission 71 is AI feature quality control only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
- performs autonomous strategy reweighting

## Consequence

DeltaGrid can now validate AI feature quality and drift before expanding AI datasets.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Autonomous trading remains:

- NO-GO
