# ADR-0060: Data Quality and Regime Intelligence Engine

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

Mission 59 added a multi-strategy research factory that produces strategy candidates. Before those candidates can move toward promotion review, DeltaGrid needs a data quality and market-regime layer.

A trading firm cannot rely on candidate alpha scores alone. It needs data confidence, liquidity regime, volatility regime, basis regime, and market risk classification.

## Decision

Add the Data Quality and Regime Intelligence Engine.

Files:

- offchain/research/data_quality_regime_intelligence_engine.py
- offchain/tests/test_data_quality_regime_intelligence_engine.py

Code commit:

- 92494a4 Add data quality regime intelligence engine

The engine reads:

- historical_public_funding_rates
- historical_public_basis_observations
- multi_strategy_research_candidates

The engine writes:

- data_quality_regime_symbol_reports
- data_quality_strategy_candidate_gates
- data_quality_regime_intelligence_reports

## Safety

Mission 60 is research and risk intelligence only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

## Consequence

DeltaGrid can now classify symbols as normal, caution, or danger before strategy candidates advance toward research promotion review.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
