# ADR-0063: Paper Trading Sandbox

## Status

Accepted

## Context

Mission 62 approved the Mission 61 shadow portfolio for paper sandbox research only.

The next step is to create a local paper-only execution environment that converts approved allocations into simulated orders, fills, and positions.

## Decision

Add the Paper Trading Sandbox.

Files:

- offchain/paper_sandbox/__init__.py
- offchain/paper_sandbox/paper_trading_sandbox.py
- offchain/tests/test_paper_trading_sandbox.py

Code commit:

- c29c9c9 Add paper trading sandbox

The sandbox reads:

- research_promotion_board_reviews
- research_promotion_board_decision_records
- shadow_portfolio_allocations
- historical_public_basis_observations

The sandbox writes:

- paper_sandbox_sessions
- paper_sandbox_orders
- paper_sandbox_fills
- paper_sandbox_positions
- paper_sandbox_reports

## Safety

Mission 63 is paper simulation only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

## Consequence

DeltaGrid can now simulate order creation, fills, positions, fees, and slippage locally without touching an exchange.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
