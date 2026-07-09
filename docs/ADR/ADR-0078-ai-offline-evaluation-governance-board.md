# ADR-0078: AI Offline Evaluation Governance Board

## Status

Accepted

## Context

Mission 77 produced offline evaluation evidence from finalized paper labels. That evidence must be reviewed before any research-only recommendation layer can consume it.

## Decision

Add the AI Offline Evaluation Governance Board.

Files:

- offchain/ai_dataset/offline_evaluation_governance_board.py
- offchain/tests/test_offline_evaluation_governance_board.py

Code commit:

- 7e6426e Add AI offline evaluation governance board

The board reads:

- ai_offline_evaluation_runs
- ai_offline_evaluation_cases
- ai_offline_evaluation_metrics
- ai_offline_evaluation_checks

The board writes:

- ai_offline_evaluation_governance_reviews
- ai_offline_evaluation_governance_evidence
- ai_offline_evaluation_governance_votes
- ai_offline_evaluation_governance_checks
- ai_offline_evaluation_governance_reports

## Safety

Mission 78 does not train a model.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
- performs autonomous strategy reweighting
- runs autonomous execution

Baseline accuracy remains label agreement only and is not profitability evidence.

## Consequence

DeltaGrid can now approve offline evaluation evidence for research-only recommendation review.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Model training remains:

- NO-GO

Autonomous trading remains:

- NO-GO
