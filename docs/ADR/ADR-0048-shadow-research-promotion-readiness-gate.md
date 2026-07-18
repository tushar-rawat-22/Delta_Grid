# ADR-0048: Shadow Research Promotion Readiness Gate

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

Mission 47 added a board-level executive daily report.

DeltaGrid now needs a formal readiness gate that decides whether the system can move to the next research stage, remain shadow-only, or stay blocked.

## Decision

Add a shadow research promotion readiness gate.

Files:

- offchain/backtest/shadow_research_promotion_readiness_gate.py
- offchain/tests/test_shadow_research_promotion_readiness_gate.py

Code commit:

- 1eaaa3d Add shadow research promotion readiness gate

The gate reads:

- shadow_research_executive_daily_reports

The gate writes:

- shadow_research_promotion_readiness_reports

It evaluates:

- report section completeness
- safety issue count
- risk review count
- live trading status
- capital deployment status
- cost-adjusted edge evidence
- close-ready observation evidence
- negative expected observation count

## Safety

The readiness gate is shadow-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All readiness decisions preserve:

- live_trading_decision = BLOCKED
- capital_deployment_decision = BLOCKED

## Verdict

Mission 48 formalizes promotion governance.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Build the real-market alpha engine under shadow-only constraints.
