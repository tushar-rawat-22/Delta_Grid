# DeltaGrid Decision Log

This file records decisions so DeltaGrid does not drift into random or silly iterations.

---

## Active Decisions

| Date | Area | Decision | Reason | Status |
|---|---|---|---|---|
| 2026-07-07 | Project isolation | Use ~/deltagrid | Prevent conflict with SkillMint | Active |
| 2026-07-07 | Phase | Local + testnet only | Avoid real capital risk | Active |
| 2026-07-07 | Contracts | Use Foundry | Strong Solidity testing | Active |
| 2026-07-07 | Offchain | Use Python 3.12 | Good for indexing and simulation | Active |
| 2026-07-07 | Python env | Use offchain/.venv | Isolated dependencies | Active |
| 2026-07-07 | Dependencies | Use requirements.txt | Reproducible setup | Active |
| 2026-07-07 | Config | Track .env.example only | Avoid secrets leak | Active |
| 2026-07-07 | Chain | Use Base Sepolia | Safe testnet monitoring | Active |
| 2026-07-07 | Database | Use SQLite locally | Simple local logging | Active |
| 2026-07-07 | Git | Use atomic commits | Clean rollback points | Active |
| 2026-07-07 | Staging | Use selective git add | Avoid accidental commits | Active |
| 2026-07-07 | Safety | No private keys or signing yet | Prevent execution risk | Active |
| 2026-07-07 | Docs | Maintain source of truth | Prevent drift | Active |

---

## Decision 001: Project Root

Decision:

- Use /Users/tusharrawat/deltagrid

Reason:

- Keep DeltaGrid separate from SkillMint.

Status:

- Active

---

## Decision 002: Python Virtual Environment

Decision:

- Use offchain/.venv

Commands:

    cd ~/deltagrid/offchain
    python3.12 -m venv .venv
    source .venv/bin/activate

Reason:

- Isolate Python dependencies.

Status:

- Active

---

## Decision 003: Dependency Snapshot

Decision:

- Use requirements.txt.

Command:

    python -m pip freeze > requirements.txt

Reason:

- Recreate environment later.

Status:

- Active

---

## Decision 004: Environment Config

Decision:

- Commit offchain/config/.env.example.
- Do not commit offchain/config/.env.

Reason:

- Prevent secret leaks.

Status:

- Active

---

## Decision 005: Monitor Before Execution

Decision:

- Build read-only monitor before simulator or execution.

Reason:

- Safe foundation before trading logic.

Status:

- Active

---

## Decision 006: Selective Git Staging

Decision:

- Use selective git add.

Actual command:

    git add offchain/indexer/chain_monitor.py offchain/config/.env.example offchain/requirements.txt

Avoid:

    git add .

Reason:

- Avoid committing secrets, DBs, logs, and unrelated files.

Status:

- Active

---

## Future Decision Template

Decision ID:

Date:

Area:

Problem:

Decision:

Alternatives considered:

Reason:

Risks:

Rollback plan:

Status:

Related files:

Related commit:

---

## Pivot Template

Date:

Current approach:

Problem:

Proposed change:

Why this is needed:

Risks:

Rollback plan:

Approved:

Pivots requiring documentation:

- changing chain
- changing RPC provider
- changing database
- adding private keys
- adding signing
- changing risk model
- changing smart contract architecture
- moving to mainnet
- using capital
- adding live execution


---

## Decision 007: Add Local Profit Simulator

Date:

- 2026-07-07

Decision:

- Build offchain/simulator/profit_simulator.py.

Reason:

- DeltaGrid needs deterministic local trade simulation before testnet execution.

Status:

- Active

Related commit:

- 691cde4 Add local profit simulator and risk engine

---

## Decision 008: Add Risk Scoring Engine

Date:

- 2026-07-07

Decision:

- Build offchain/risk/risk_engine.py.

Reason:

- Every simulated opportunity must be approved or rejected by explicit risk rules before any future execution layer.

Status:

- Active

Related commit:

- 691cde4 Add local profit simulator and risk engine


---

## Decision 009: Add Market Data Schema

Date:

- 2026-07-07

Decision:

- Build offchain/db/schema.py.

Reason:

- DeltaGrid needs structured storage before real pool indexing, route discovery, or testnet simulations.

Status:

- Active

Related commit:

- 3d75dc6 Add market data schema and opportunity store

---

## Decision 010: Add Opportunity Store

Date:

- 2026-07-07

Decision:

- Store simulated opportunities and risk decisions in dedicated database tables.

Reason:

- Every simulated opportunity should be linked to a risk decision for traceability.

Status:

- Active

Related commit:

- 3d75dc6 Add market data schema and opportunity store
