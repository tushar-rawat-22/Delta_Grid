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


---

## Decision 011: Connect Monitor to Market Schema

Date:

- 2026-07-07

Decision:

- Update chain_monitor.py to write block and gas snapshots into the new market schema.

Reason:

- DeltaGrid needs one consistent database layer before adding pool indexing or route discovery.

Status:

- Active

Related commit:

- 4737dca Connect chain monitor to market schema


---

## Decision 012: Add Token and Pool Seed Registry

Date:

- 2026-07-07

Decision:

- Add JSON seed files and a seed loader for known tokens and pools.

Reason:

- DeltaGrid needs stable local token and pool data before route building or opportunity detection.

Status:

- Active

Related commit:

- 16e6824 Add token and pool seed registry


---

## Decision 013: Add Pool Price Snapshot Simulator

Date:

- 2026-07-07

Decision:

- Add local simulated price snapshots for seeded pools.

Reason:

- DeltaGrid needs pool prices before route building and opportunity detection.

Status:

- Active

Related commit:

- c4bcbfd Add pool price snapshot simulator


---

## Decision 014: Add Local Route Builder

Date:

- 2026-07-07

Decision:

- Add a local route builder that creates two-hop token routes from latest pool price snapshots.

Reason:

- DeltaGrid needs route candidates before opportunity detection.

Status:

- Active

Related commit:

- e73b359 Add local route builder


---

## Decision 015: Add Historical Data and Backtest Framework

Date:

- 2026-07-07

Decision:

- Add historical candle storage, backtest run storage, trade storage, metrics, and baseline backtest engine.

Reason:

- DeltaGrid must prove strategies through reproducible backtests before live testing.

Status:

- Active

Related commit:

- 7b863f5 Add historical data and backtest framework

---

## Decision 016: Reject MA Crossover Baseline for Live Use

Date:

- 2026-07-07

Decision:

- Do not approve the MA crossover baseline for live trading.

Reason:

- Backtest showed negative return, high drawdown, negative Sharpe, poor profit factor, and weak win rate.

Status:

- Active

Verdict:

- NO-GO


---

## Decision 017: Add Strategy Regime Analysis

Date:

- 2026-07-07

Decision:

- Add market regime labeling and regime-level strategy performance metrics.

Reason:

- DeltaGrid must identify which market conditions help or destroy a strategy before approving live testing.

Status:

- Active

Related commit:

- 64644d1 Add strategy regime analysis

---

## Decision 018: Reject MA Crossover Across Regimes

Date:

- 2026-07-07

Decision:

- Reject the MA crossover baseline across market regimes.

Reason:

- The strategy fails in bear, sideways, and low-volatility regimes.
- The profitable bull regime still does not pass strict approval rules.
- Sample sizes are not strong enough for confidence.

Status:

- Active

Verdict:

- NO-GO


---

## Decision 019: Add Optimized Opportunity Detector

Date:

- 2026-07-08

Decision:

- Add a strict opportunity detector that validates route candidates before any execution logic.

Reason:

- DeltaGrid must reject fake opportunities before capital is ever at risk.

Status:

- Active

Related commit:

- 3502dae Add optimized opportunity detector

---

## Decision 020: Reject Current Conversion Routes

Date:

- 2026-07-08

Decision:

- Reject current WETH to DAI and DAI to WETH routes as profit opportunities.

Reason:

- They are not closed-loop arbitrage routes.

Status:

- Active

Verdict:

- NO-GO


---

## Decision 021: Add Closed-Loop Route Builder

Date:

- 2026-07-08

Decision:

- Add a closed-loop route builder that creates A to B to C to A route candidates.

Reason:

- Opportunity detection requires closed-loop routes before arbitrage-style profit can be evaluated.

Status:

- Active

Related commit:

- bb3ad35 Add closed-loop route builder

---

## Decision 022: Keep Approved Closed-Loop Opportunity Research-Only

Date:

- 2026-07-08

Decision:

- Do not approve live trading even though one simulated closed-loop route was approved.

Reason:

- The approved opportunity is synthetic.
- It has not been tested on real historical market data.
- It has not passed testnet execution.
- It has not passed mainnet-fork execution.
- Capital risk remains forbidden.

Status:

- Active

Verdict:

- RESEARCH_GO
- LIVE_NO_GO


---

## Decision 023: Add Real Historical Market Data Ingestion

Date:

- 2026-07-08

Decision:

- Add Binance Spot historical candle ingestion.

Reason:

- DeltaGrid needs real market data before any strategy can be trusted.

Status:

- Active

---

## Decision 024: Keep MA Crossover Research-Only

Date:

- 2026-07-08

Decision:

- Do not approve MA crossover for live trading.

Reason:

- positive return but weak risk-adjusted performance
- high drawdown
- weak Sharpe
- weak profit factor
- poor bear and sideways performance

Verdict:

- RESEARCH_ONLY
- LIVE_NO_GO


---

## Decision 025: Add Strategy Validation Engine

Date:

- 2026-07-08

Decision:

- Add benchmark comparison and walk-forward validation.

Reason:

- A single profitable backtest is not enough.

Status:

- Active

Related commit:

- 47ac51b Add strategy validation engine

---

## Decision 026: Reject MA Crossover After Walk-Forward Validation

Date:

- 2026-07-08

Decision:

- Keep MA crossover rejected.

Reason:

- drawdown too high
- excess return too small
- walk-forward validation failed
- 0 out of 5 splits passed

Verdict:

- STRATEGY_NO_GO
- LIVE_NO_GO


---

## Decision 027: Add Strategy Candidate Lab

Date:

- 2026-07-08

Decision:

- Add a multi-strategy candidate lab.

Reason:

- DeltaGrid needs to test multiple strategies instead of depending on one MA crossover baseline.

Status:

- Active

Related commit:

- f7b06b9 Add strategy candidate lab

---

## Decision 028: Reject All Mission 15 Candidates

Date:

- 2026-07-08

Decision:

- Reject all Mission 15 strategy candidates for live trading.

Reason:

- approved_count is 0
- best candidate exceeded drawdown limit
- global verdict is REJECT_ALL_NO_LIVE_TRADING

Verdict:

- REJECT_ALL
- LIVE_NO_GO
