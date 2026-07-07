# ADR-0012: Closed-Loop Route Builder and Opportunity Validation

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 11 correctly rejected existing route candidates because they were conversion routes, not closed-loop arbitrage routes.

Existing routes:

- WETH to DAI
- DAI to WETH

These cannot be treated as profit-valid arbitrage opportunities.

Mission 12 adds closed-loop route construction.

Target route shape:

- A to B to C to A

Example:

- WETH to USDC to DAI to WETH

---

## Decision

Add a closed-loop route builder.

Files changed:

- offchain/config/seed_pools.json
- offchain/simulator/price_snapshot_simulator.py
- offchain/simulator/closed_loop_route_builder.py
- offchain/tests/test_closed_loop_route_builder.py

Commit:

- bb3ad35 Add closed-loop route builder

---

## Added Pool

Added third demo pool:

- DAI_DEMO to WETH

Pool address:

- 0x0000000000000000000000000000000000003000

Purpose:

- enables WETH to USDC to DAI to WETH closed-loop route

---

## Simulated Prices

Current simulated prices:

- WETH to USDC: 3000
- USDC to DAI: 1
- DAI to WETH: 0.00034

Forward loop:

- WETH to USDC to DAI to WETH
- multiplier: 1.02000

Reverse loop:

- WETH to DAI to USDC to WETH
- multiplier: 0.98039215686274509803921568627450980392156862745096

---

## Verified Database Output

Counts:

- pools: 3
- pool_price_snapshots: 5
- route_candidates: 4
- opportunity_detections: 6

Latest closed-loop routes:

- route 3: multiplier 1.02000
- route 4: multiplier 0.98039215686274509803921568627450980392156862745096

---

## Opportunity Detector Result

Approved:

- route 3
- opportunity_type: closed_loop_arbitrage
- gross_edge_bps: 200.00000
- total_cost_bps: 50
- net_edge_bps: 150.00000
- risk_score: 88

Rejected:

- route 4
- opportunity_type: closed_loop_arbitrage
- gross_edge_bps: -196.0784313725490196078431372549019607843
- net_edge_bps: -246.0784313725490196078431372549019607843
- reason: gross_edge_not_positive
- reason: net_edge_below_minimum

---

## Investment Committee Verdict

Closed-loop route framework:

- GO

Simulated approved opportunity:

- RESEARCH_GO

Live trading:

- NO-GO

Reason:

- opportunity is synthetic
- no real historical market data validation yet
- no testnet execution yet
- no fork simulation yet
- no real capital approval

---

## Safety Status

Still safe:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
