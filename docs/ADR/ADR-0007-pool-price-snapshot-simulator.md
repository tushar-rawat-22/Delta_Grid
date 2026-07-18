# ADR-0007: Pool Price Snapshot Simulator

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

DeltaGrid already had:

- token seed registry
- pool seed registry
- market database schema
- opportunity store
- risk engine
- local simulator

The next step was to generate local pool price snapshots.

This is required before:

- route building
- opportunity detection
- arbitrage simulation
- pool graph construction

---

## Decision

Add a local pool price snapshot simulator.

Files changed:

- offchain/db/schema.py
- offchain/simulator/price_snapshot_simulator.py
- offchain/tests/test_price_snapshot_simulator.py

Commit:

- c4bcbfd Add pool price snapshot simulator

---

## Database Table Added

Table:

- pool_price_snapshots

Stores:

- pool_id
- chain_id
- protocol
- pool_address
- token0_address
- token1_address
- price_token1_per_token0
- price_token0_per_token1
- liquidity_score
- source
- block_number
- created_at_utc

---

## Verified Output

Database counts:

- pools 2
- pool_price_snapshots 2

Latest snapshots:

- WETH/USDC_DEMO price: 3000
- USDC_DEMO/DAI_DEMO price: 1

Block used:

- 43831432

Source:

- local_simulator

---

## Safety Status

Still safe:

- no private keys
- no signing
- no trades
- no real capital
- local simulated prices only

---

## Consequences

DeltaGrid can now store local price snapshots for seeded pools.

This prepares the project for:

- route builder
- opportunity detector
- arbitrage simulation
- price comparison
- pool graph analysis
