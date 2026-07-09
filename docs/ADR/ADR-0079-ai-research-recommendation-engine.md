# ADR-0079: AI Research Recommendation Engine

## Status

Accepted

## Context

Mission 78 approved Mission 77 offline evaluation evidence for research-only recommendation handoff.

DeltaGrid needs a recommendation engine that can produce research-only recommendations without creating live signals, training models, unlocking capital, or trading.

## Decision

Add the AI Research Recommendation Engine.

Files:

- offchain/ai_dataset/research_recommendation_engine.py
- offchain/tests/test_research_recommendation_engine.py

Code commit:

- cc49ec5 Add AI research recommendation engine

The engine reads:

- ai_offline_evaluation_governance_reviews
- ai_offline_evaluation_governance_evidence
- ai_offline_evaluation_governance_votes
- ai_offline_evaluation_governance_checks

The engine writes:

- ai_research_recommendation_runs
- ai_research_recommendation_items
- ai_research_recommendation_checks
- ai_research_recommendation_reports

## Safety

Mission 79 does not train a model and does not create live trading signals.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
- performs autonomous strategy reweighting
- runs autonomous execution

Every recommendation requires human review.

Baseline accuracy remains label agreement only and is not profitability evidence.

## Consequence

DeltaGrid can now create research-only recommendations for human review.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Model training remains:

- NO-GO

Autonomous trading remains:

- NO-GO
