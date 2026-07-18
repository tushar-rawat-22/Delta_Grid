# ADR-0006: Token and Pool Seed Registry

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

DeltaGrid needed a safe way to load known tokens and pools into the local database.

This must happen before:

- route building
- opportunity detection
- pool pricing
- reserve simulation

---

## Decision

Create local seed files and a seed loader.

Files created:

- offchain/config/seed_tokens.json
- offchain/config/seed_pools.json
- offchain/db/seed_registry.py
- offchain/tests/test_seed_registry.py

Commit:

- 16e6824 Add token and pool seed registry

---

## Seeded Tokens

- WETH
- USDC_DEMO
- DAI_DEMO

Total:

- 3 tokens

---

## Seeded Pools

Protocol:

- demo-uniswap-v3

Total:

- 2 pools

---

## Verified Database Counts

- chains 1
- tokens 3
- pools 2

---

## Safety Status

Still safe:

- no private keys
- no signing
- no trades
- no real capital
- local seed data only

---

## Consequences

DeltaGrid now has a reusable registry seed layer.

This prepares the project for:

- route builder
- price snapshot simulator
- opportunity detector
- pool graph construction
