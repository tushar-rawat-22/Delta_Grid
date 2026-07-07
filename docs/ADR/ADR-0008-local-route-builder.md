# ADR-0008: Local Route Builder

## Status

Accepted

## Date

2026-07-07

---

## Context

DeltaGrid already had:

- seeded tokens
- seeded pools
- pool price snapshots
- market schema
- local simulator
- risk engine

The next step was to build possible local token routes.

This is required before:

- opportunity detection
- arbitrage simulation
- route ranking
- strategy scoring

---

## Decision

Add a local route builder.

Files changed:

- offchain/db/schema.py
- offchain/simulator/route_builder.py
- offchain/tests/test_route_builder.py

Commit:

- e73b359 Add local route builder

---

## Database Table Added

Table:

- route_candidates

Stores:

- chain_id
- start_token_address
- end_token_address
- hops
- route_json
- estimated_output_per_input
- min_liquidity_score
- source
- block_number
- created_at_utc

---

## Verified Output

Database counts:

- pool_price_snapshots 2
- route_candidates 2

Latest routes:

- WETH to DAI_DEMO
- DAI_DEMO to WETH

Verified values:

- WETH to DAI_DEMO estimated output: 3000
- DAI_DEMO to WETH estimated output: 0.0003333333333333333333333333333333333333333
- min liquidity score: 80
- source: local_route_builder
- block number: 43831432

---

## Verified Tests

Command:

    python -m unittest discover -s tests -v

Result:

    Ran 13 tests in 0.087s
    OK

---

## Safety Status

Still safe:

- no private keys
- no signing
- no trades
- no real capital
- local route simulation only

---

## Consequences

DeltaGrid can now build local route candidates from pool snapshots.

This prepares the project for:

- opportunity detection
- route profitability checks
- opportunity ranking
- risk-scored simulations
