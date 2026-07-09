# ADR-0059: Multi-Strategy Research Factory

## Status

Accepted

## Context

Mission 58 created the Shadow Research Control Plane and documentation registry.

DeltaGrid now needs to stop depending on one funding/basis hypothesis and operate like a broader quant research lab.

## Decision

Add the Multi-Strategy Research Factory.

Files:

- offchain/research/__init__.py
- offchain/research/multi_strategy_research_factory.py
- offchain/tests/test_multi_strategy_research_factory.py

Code commit:

- 271e249

Strategy families:

- funding/basis carry
- funding-rate momentum
- basis mean reversion
- volatility regime filter
- cross-symbol relative strength

Tables:

- multi_strategy_research_registry
- multi_strategy_research_candidates
- multi_strategy_research_factory_reports

## Safety

Mission 59 is research-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

## Consequence

DeltaGrid now has a multi-strategy research factory that can generate promotion shortlist, watchlist, rejection, and data-insufficient candidates.

Live trading remains NO-GO.

Capital deployment remains NO-GO.
