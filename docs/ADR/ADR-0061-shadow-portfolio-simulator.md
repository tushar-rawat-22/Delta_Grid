# ADR-0061: Shadow Portfolio Simulator

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

Mission 59 created a multi-strategy research factory.
Mission 60 created data quality and regime gates.

The next step is to convert candidate-level research into a portfolio-level shadow simulation.

A real trading firm does not approve isolated candidates directly. It first checks portfolio allocation, symbol concentration, strategy concentration, and simulated drawdown.

## Decision

Add the Shadow Portfolio Simulator.

Files:

- offchain/portfolio/__init__.py
- offchain/portfolio/shadow_portfolio_simulator.py
- offchain/tests/test_shadow_portfolio_simulator.py

Code commit:

- 545fe15 Add shadow portfolio simulator

The simulator reads:

- data_quality_strategy_candidate_gates

The simulator writes:

- shadow_portfolio_simulations
- shadow_portfolio_allocations
- shadow_portfolio_risk_reports

## Safety

Mission 61 is simulation-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

## Consequence

DeltaGrid can now evaluate whether candidate research survives portfolio construction and concentration limits.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
