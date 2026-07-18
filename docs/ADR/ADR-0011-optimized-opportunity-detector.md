# ADR-0011: Optimized Opportunity Detector

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

DeltaGrid now has:

- route candidates
- price snapshots
- backtest framework
- regime analysis
- risk-first development rules

Mission 11 adds an optimized opportunity detector.

The detector must not treat a simple conversion route as profit.

Example:

- WETH to DAI
- DAI to WETH

These are not automatically arbitrage opportunities.

---

## Decision

Add an optimized opportunity detector.

Files changed:

- offchain/db/schema.py
- offchain/detector/__init__.py
- offchain/detector/opportunity_detector.py
- offchain/tests/test_opportunity_detector.py

Commit:

- 3502dae Add optimized opportunity detector

---

## Table Added

- opportunity_detections

Stores:

- route candidate ID
- opportunity type
- gross edge
- fee cost
- slippage cost
- gas cost
- safety buffer
- net edge
- liquidity score
- risk score
- status
- rejection reasons
- assumptions
- source
- block number

---

## Detector Rules

The detector requires:

- closed-loop route
- positive gross edge
- net edge above minimum threshold
- liquidity score above minimum threshold
- realistic cost assumptions
- explicit safety buffer

Current safety settings:

- fee_bps 10
- slippage_bps 10
- gas_cost_bps 10
- safety_buffer_bps 20
- min_net_edge_bps 50
- min_liquidity_score 70

---

## Verified Result

Command:

    python detector/opportunity_detector.py \
      --fee-bps 10 \
      --slippage-bps 10 \
      --gas-cost-bps 10 \
      --safety-buffer-bps 20 \
      --min-net-edge-bps 50 \
      --min-liquidity-score 70

Output:

- routes_seen: 2
- detections_created: 2
- approved: 0
- rejected: 2

Reason:

- not_closed_loop_route

---

## Test Result

Command:

    python -m unittest discover -s tests -v

Result:

    Ran 20 tests in 0.549s
    OK

---

## Investment Committee Verdict

Framework:

- GO

Current detected opportunities:

- NO-GO

Live trading:

- NO-GO

Reason:

- current routes are conversion routes
- no closed-loop arbitrage route exists yet
- no live edge is proven
- capital must not be risked

---

## Safety Status

Still safe:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
