# ADR-0005: Chain Monitor Market Schema Integration

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

- safe chain monitor
- market data schema
- opportunity store
- risk engine
- simulator

The monitor was still writing mainly to the old block_logs table.

Mission 5 connected the monitor to the new market schema.

---

## Decision

Update chain_monitor.py so every safe block snapshot writes into:

- block_logs
- chains
- blocks
- gas_snapshots

Files changed:

- offchain/indexer/__init__.py
- offchain/indexer/chain_monitor.py
- offchain/tests/test_chain_monitor_schema_integration.py

Commit:

- 4737dca Connect chain monitor to market schema

---

## Verified Tests

Command:

    python -m unittest discover -s tests -v

Result:

    Ran 8 tests in 0.025s
    OK

---

## Verified Live Monitor Run

Command:

    python indexer/chain_monitor.py --once

Confirmed output:

    Connected to chain_id=84532
    block=43831432
    gas=6000000

---

## Verified Database Counts

After live monitor run:

- block_logs 5
- chains 1
- blocks 2
- gas_snapshots 2

Latest real block stored:

- chain_id 84532
- block_number 43831432
- gas_price_wei 6000000

---

## Safety Status

Still safe:

- no private keys
- no signing
- no trades
- no real capital
- local database writes only

---

## Consequences

DeltaGrid now has a connected monitoring pipeline:

    RPC read
    -> chain_monitor.py
    -> market schema
    -> blocks table
    -> gas_snapshots table

This prepares the project for real pool/event indexing later.
