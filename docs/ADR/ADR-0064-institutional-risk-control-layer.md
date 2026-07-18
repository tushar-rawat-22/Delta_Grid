# ADR-0064: Institutional Risk Control Layer

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

Mission 63 created a paper-only execution sandbox with simulated orders, fills, positions, fees, and slippage.

Before paper observation can continue, DeltaGrid needs an institutional-style risk control layer that enforces hard limits on exposure, cost, order integrity, diversification, and safety invariants.

## Decision

Add the Institutional Risk Control Layer.

Files:

- offchain/risk/__init__.py
- offchain/risk/institutional_risk_control.py
- offchain/tests/test_institutional_risk_control.py

Code commit:

- 7d01993 Add institutional risk control layer

The risk layer reads:

- paper_sandbox_sessions
- paper_sandbox_orders
- paper_sandbox_positions

The risk layer writes:

- institutional_risk_control_reviews
- institutional_risk_limit_checks
- institutional_risk_decision_records

## Safety

Mission 64 is risk governance only.

If approved, the approval scope is:

- controlled paper observation only

It is explicitly not approval for:

- live trading
- real capital
- private keys
- exchange orders
- signing

## Consequence

DeltaGrid can now enforce hard institutional risk limits before paper observation continues.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
