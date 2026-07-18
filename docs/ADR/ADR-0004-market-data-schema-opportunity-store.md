# ADR-0004: Market Data Schema and Opportunity Store

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

DeltaGrid had already completed:

- smart contract foundation
- safe offchain chain monitor
- source-of-truth documentation
- local profit simulator
- risk scoring engine

The next required foundation was a structured local database layer.

Before adding real DEX routes, pool indexing, arbitrage discovery, or testnet simulations, DeltaGrid needs a clean place to store:

- chains
- blocks
- gas snapshots
- tokens
- pools
- simulated opportunities
- risk decisions

Without this schema, future work would become messy and random.

---

## Decision

Create a local market data schema and opportunity store.

Files created:

- offchain/db/__init__.py
- offchain/db/schema.py
- offchain/db/opportunity_store_demo.py
- offchain/tests/test_market_schema.py

Commit:

- 3d75dc6 Add market data schema and opportunity store

---

## Database Tables Added

The schema creates these tables:

- schema_migrations
- chains
- blocks
- gas_snapshots
- tokens
- pools
- simulated_opportunities
- risk_decisions

---

## Table Purpose

### chains

Stores supported chains.

Example:

- Base Sepolia
- chain_id 84532
- RPC URL

### blocks

Stores observed block numbers.

### gas_snapshots

Stores gas price observations.

### tokens

Stores token metadata.

Fields include:

- chain_id
- address
- symbol
- decimals

### pools

Stores DEX pool metadata.

Fields include:

- chain_id
- protocol
- pool_address
- token0_address
- token1_address
- fee_bps

### simulated_opportunities

Stores simulated opportunity outputs.

Fields include:

- chain_id
- block_number
- opportunity_type
- route_json
- gross_profit_wei
- gas_cost_wei
- flash_fee_wei
- slippage_cost_wei
- total_cost_wei
- net_profit_wei

### risk_decisions

Stores risk decisions linked to simulated opportunities.

Fields include:

- opportunity_id
- risk_score
- approved
- reasons_json

---

## Confirmed Verification

Database table counts showed:

- chains 1
- blocks 1
- gas_snapshots 1
- tokens 2
- pools 1
- simulated_opportunities 1
- risk_decisions 1

Latest opportunity:

- id 1
- chain_id 84532
- block_number 43829863
- opportunity_type demo_arbitrage
- gross_profit_wei 5000000000000000
- total_cost_wei 2000000000000000
- net_profit_wei 3000000000000000

Latest risk decision:

- id 1
- opportunity_id 1
- risk_score 100
- approved 1
- reasons_json []

---

## Safety Status

This module uses:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet deployment

It is local database storage only.

---

## Consequences

Positive:

- DeltaGrid now has structured market storage.
- Future indexers can write into stable tables.
- Future simulators can store opportunity results.
- Risk decisions are linked to opportunities.
- The system is ready for deeper market data modules.

Tradeoffs:

- SQLite is still local-only.
- The pool/token data is demo data.
- No real DEX pool indexing yet.
- No live opportunity discovery yet.
- No production migrations yet.

---

## Review Trigger

Review this ADR when adding:

- real DEX pool indexing
- historical block sync
- PostgreSQL migration
- multi-chain support
- route discovery
- opportunity ranking
- cloud deployment
- production migration tooling
