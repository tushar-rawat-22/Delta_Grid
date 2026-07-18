# ADR-0062: Research Promotion Board

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
Mission 60 added data quality and regime gates.
Mission 61 added a shadow portfolio simulator.

The next step is a governance layer that decides whether a shadow portfolio is ready for the next simulated research phase.

## Decision

Add the Research Promotion Board.

Files:

- offchain/governance/__init__.py
- offchain/governance/research_promotion_board.py
- offchain/tests/test_research_promotion_board.py

Code commit:

- bf9acf6

The board reads:

- shadow_portfolio_simulations
- shadow_portfolio_allocations
- shadow_portfolio_risk_reports

The board writes:

- research_promotion_board_reviews
- research_promotion_board_evidence_items
- research_promotion_board_decision_records

## Safety

Mission 62 is governance-only.

If approved, the approval scope is:

- paper sandbox research only

It is explicitly not approval for:

- live trading
- real capital
- private keys
- exchange orders
- signing

## Consequence

DeltaGrid now has a board-style promotion gate before any paper sandbox phase.

Live trading remains NO-GO.

Capital deployment remains NO-GO.
