# ADR-0003: Local Profit Simulator and Risk Engine

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

## Date

2026-07-07

---

## Context

DeltaGrid needed a safe local simulation layer after completing:

- smart contract foundation
- safe offchain chain monitor
- project source-of-truth documentation

Before any testnet execution, transaction signing, private key usage, or real capital, the system must be able to evaluate simulated trades locally.

The simulator must answer:

- What is the gross profit?
- What is the gas cost?
- What is the flash-loan fee?
- What is the slippage cost?
- What is the final net profit?
- Should this opportunity be approved or rejected?
- Why was it rejected?

---

## Decision

Build a local-only profit simulator and risk scoring engine.

Files created:

- offchain/risk/__init__.py
- offchain/risk/risk_engine.py
- offchain/simulator/__init__.py
- offchain/simulator/profit_simulator.py
- offchain/tests/__init__.py
- offchain/tests/test_risk_engine.py

Commit:

- 691cde4 Add local profit simulator and risk engine

---

## Risk Engine Responsibilities

The risk engine evaluates simulated trades using:

- gross profit
- gas cost
- flash-loan fee
- slippage cost
- slippage basis points
- estimated success probability
- minimum net profit threshold
- maximum gas-to-gross-profit ratio
- minimum risk score

It returns:

- approved true/false
- risk score
- net profit
- total cost
- rejection reasons

---

## Simulator Responsibilities

The simulator runs deterministic local cases.

Current cases:

1. safe_trade
2. bad_cost_trade
3. high_slippage_trade
4. low_confidence_trade

It logs outputs to SQLite table:

- simulation_logs

Stored fields include:

- timestamp_utc
- gross_profit_wei
- gas_cost_wei
- flash_fee_wei
- slippage_cost_wei
- total_cost_wei
- net_profit_wei
- risk_score
- approved
- reasons_json

---

## Confirmed Test Output

Command:

    python -m unittest discover -s tests -v

Result:

    Ran 4 tests in 0.000s
    OK

Tests passed:

- test_safe_trade_is_approved
- test_trade_rejected_for_high_slippage
- test_trade_rejected_for_low_confidence
- test_trade_rejected_when_costs_exceed_profit

---

## Confirmed Simulator Output

The simulator correctly produced:

- safe_trade approved
- bad_cost_trade rejected
- high_slippage_trade rejected
- low_confidence_trade rejected

Important result:

A profitable trade can still be rejected if:

- slippage is too high
- confidence is too low
- gas cost is too high
- net profit is below threshold

This is intentional risk discipline.

---

## Confirmed Database Logging

The simulator wrote rows into:

- offchain/deltagrid.db

Table:

- simulation_logs

Verified examples:

- approved trade stored with risk_score 100 and approved 1
- rejected trades stored with approved 0
- rejection reasons stored as JSON

---

## Safety Status

This module uses:

- no private keys
- no signing
- no live trading
- no real capital
- no mainnet deployment

It is local simulation only.

---

## Consequences

Positive:

- DeltaGrid now has local trade evaluation.
- Risk scoring is separated from monitoring.
- Simulator outputs are deterministic.
- Rejection reasons are explainable.
- Database logging works for simulation results.

Tradeoffs:

- Values are hardcoded examples for now.
- No real DEX pricing yet.
- No pool reserves yet.
- No oracle-based pricing yet.
- No route discovery yet.

---

## Review Trigger

Review this ADR when adding:

- live DEX pool data
- route simulation
- Uniswap/Aave integrations
- gas estimation from RPC
- slippage model upgrades
- confidence model upgrades
- testnet transaction simulation
- private key handling
- any real execution
