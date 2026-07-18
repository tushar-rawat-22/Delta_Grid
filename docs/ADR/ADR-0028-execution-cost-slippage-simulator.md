# ADR-0028: Execution Cost + Slippage Simulator

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

2026-07-08

---

## Context

Mission 27 added liquidation and leverage risk modeling.

Mission 28 adds execution cost and slippage modeling before expanding to multi-symbol opportunity discovery.

A funding strategy cannot be promoted unless expected edge survives fees, spread, slippage, participation, and liquidity penalties.

This mission still does not execute trades.

---

## Decision

Add execution cost + slippage simulator.

Files:

- offchain/backtest/execution_cost_slippage_simulator.py
- offchain/tests/test_execution_cost_slippage_simulator.py

Code commit:

- d85a533 Add execution cost slippage simulator

---

## Tables Added

- execution_cost_slippage_results
- execution_cost_slippage_summary

---

## Cost Logic

The simulator evaluates:

- spot order notional
- perpetual order notional
- gross notional
- fee cost
- spread cost
- slippage cost
- participation rate
- liquidity penalty
- combined round-trip cost
- expected funding edge
- net expected edge
- edge-to-cost ratio
- GO / NO-GO verdict

---

## Mission 28 Verification

Run label:

- mission_28_execution_cost_slippage_simulator

Source run:

- mission_23_funding_basis_ingestion

Latest run summary:

- small_10k_liquid_low_impact|7|10000|10000|0.075500|0.029862000|-0.045638000|0.3955231788079470198675496688741721854305|NO_GO_EDGE_BELOW_COST|WAIT_FOR_BETTER_EDGE_TO_COST_RATIO || medium_50k_balanced_impact|7|50000|50000|0.1400|0.029862000|-0.110138000|0.21330|NO_GO_EDGE_BELOW_COST|WAIT_FOR_BETTER_EDGE_TO_COST_RATIO || large_250k_stress_impact|7|250000|250000|3.952500|0.029862000|-3.922638000|0.007555218216318785578747628083491461100569|NO_GO_SPOT_ORDER_TOO_LARGE|REDUCE_SPOT_ORDER_SIZE_OR_REQUIRE_MORE_DEPTH

---

## Investment Committee Verdict

Execution cost + slippage simulator:

- GO

Current scenarios:

- scenario verdicts depend on real funding edge and assumed costs

Live trading:

- NO-GO

Reason:

- this is still research-only
- no live broker/exchange quote stream
- no real order book execution
- no fill simulator connected to live liquidity
- no position sizing engine
- no risk governor
- no private keys
- no real trades

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
