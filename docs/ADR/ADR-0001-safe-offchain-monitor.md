# ADR-0001: Safe Offchain Chain Monitor

## Status

Accepted

## Date

2026-07-07

---

## Context

DeltaGrid needs an offchain monitoring layer before any strategy, simulation, execution, or capital-related logic.

The first offchain module must observe blockchain state safely.

It must not use:

- private keys
- signing
- real funds
- live trading
- automated execution

---

## Decision

Build a Python-based safe chain monitor.

File:

- offchain/indexer/chain_monitor.py

Use a local virtual environment:

- offchain/.venv

Use config template:

- offchain/config/.env.example

Use local config:

- offchain/config/.env

Use local database:

- offchain/deltagrid.db

Use first network:

- Base Sepolia
- chain_id=84532
- RPC_URL=https://sepolia.base.org

---

## Commands Used

Create environment:

    cd ~/deltagrid/offchain
    python3.12 -m venv .venv
    source .venv/bin/activate

Install dependencies:

    python -m pip install --upgrade pip
    python -m pip install web3 python-dotenv requests pandas pydantic sqlalchemy

Freeze dependencies:

    python -m pip freeze > requirements.txt

Run monitor:

    python indexer/chain_monitor.py

---

## Confirmed Output

    DeltaGrid Chain Monitor
    Mode: safe monitoring only
    No private keys. No signing. No real trades.
    RPC: https://sepolia.base.org
    Connected to chain_id=84532

Confirmed blocks:

- 43829854
- 43829857
- 43829860
- 43829863

Confirmed database row:

- ('2026-07-07T12:39:57.301908+00:00', 84532, 43829854, '6000000')

---

## Reasoning

This is the correct first offchain step because it proves:

- RPC connectivity works
- Python environment works
- environment config works
- SQLite logging works
- testnet monitoring works
- no private key is needed
- no transaction is signed

---

## Consequences

Positive:

- Safe data foundation created
- No capital risk
- No key-management risk
- Easy local debugging
- Easy future extension

Tradeoffs:

- SQLite is local-only
- public RPC may be rate-limited
- monitor currently logs only block and gas data
- no DEX event indexing yet

---

## Alternatives Considered

Alternative 1:

- Start with trading execution
- Rejected because execution before monitoring is unsafe

Alternative 2:

- Start with PostgreSQL
- Deferred because SQLite is enough for local phase

Alternative 3:

- Start with mainnet monitoring
- Rejected because testnet is safer

Alternative 4:

- Use Node.js instead of Python
- Deferred because Python is better for data and risk workflows

---

## Review Trigger

Review this ADR when adding:

- event indexing
- DEX pool indexing
- PostgreSQL
- paid RPC
- multiple chains
- transaction simulation
- risk scoring
- signing functionality
