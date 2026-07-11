# ADR-0084.8: Alpha Candidate Promotion Pack

Date: 2026-07-11

Status: Accepted

## Context

Mission 84.7 evaluated 72 synthetic-fixture strategy candidates across
deterministic walk-forward windows. Thirty-five candidates passed the fixture
robustness rules, while thirty-seven were blocked.

Synthetic fixture evidence validates the research pipeline but is insufficient
for model promotion, live trading, capital deployment, or profitability claims.

## Decision

Mission 84.8 performs deterministic candidate review and creates a provisional
fixture-only alpha research registry.

Only candidates with robust source status, sufficient windows, positive median
fixture return, acceptable drawdown and dispersion, cash-baseline
outperformance, and intact inherited safety locks may enter the registry.

Registry status:

`PROVISIONAL_ALPHA_RESEARCH_CANDIDATE_FIXTURE_ONLY_UNVALIDATED`

This is research classification only. Mission 85 remains paused. Registered
candidates must next undergo local/free real-data replication in Mission 84.9.

## Safety Boundary

No live trading, live signals, exchange orders, real capital, private keys,
signing, paid APIs, model training, model artifacts, model promotion,
capital-linked strategy reweighting, or profitability claims.

## Consequences

Mission 84.9 may consume only provisional registry entries. Held candidates
remain blocked.
