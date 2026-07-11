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


---

## Decision 029: Add Drawdown Control Lab

Date:

- 2026-07-08

Decision:

- Add drawdown control testing for strategy candidates.

Reason:

- Mission 15 produced high returns but unacceptable drawdown.

Status:

- Active

Related commit:

- a74134e Add drawdown control lab

---

## Decision 030: Reject Mission 16 Candidates

Date:

- 2026-07-08

Decision:

- Reject all Mission 16 candidates for live trading.

Reason:

- approved_count is 0
- best return candidate still exceeded drawdown limit
- lowest drawdown candidate underperformed buy-and-hold

Verdict:

- REJECT_ALL
- LIVE_NO_GO

---

## Decision 031: Add Walk-Forward Candidate Lab

Date:

- 2026-07-08

Decision:

- Add walk-forward validation for all candidate strategies.

Reason:

- Full-period performance can be misleading.
- Strategy candidates must be tested across multiple unseen windows.

Status:

- Active

Related commit:

- 0ef95c8 Add walk-forward candidate lab

---

## Decision 032: Reject Mission 17 Candidates

Date:

- 2026-07-08

Decision:

- Reject all Mission 17 candidates for live trading.

Reason:

- approved_count is 0
- best candidate had 0 GO splits
- global verdict is REJECT_ALL_NO_LIVE_TRADING

Verdict:

- REJECT_ALL
- LIVE_NO_GO

---

## Decision 033: Add Strategy Diagnostics

Date:

- 2026-07-08

Decision:

- Add diagnostic failure attribution for strategy candidates.

Reason:

- Rejected strategies must explain why they failed.
- Future strategy work should be based on failure causes, not random tuning.

Status:

- Active

Related commit:

- fd38244 Add strategy diagnostics

---

## Decision 034: Prioritize Walk-Forward Stability

Date:

- 2026-07-08

Decision:

- Treat weak walk-forward stability as the primary blocker.

Reason:

- All 7 candidates failed primarily due to WEAK_WALK_FORWARD_STABILITY.

Verdict:

- STABILITY_REWORK_REQUIRED
- LIVE_NO_GO

---

## Decision 035: Add Stability Rework Lab

Date:

- 2026-07-08

Decision:

- Add stability rework lab to test stricter controlled MA variants.

Reason:

- Mission 18 found weak walk-forward stability as the primary failure.
- Mission 19 must test whether stability can be improved without overfitting.

Status:

- Active

Related commit:

- f93a531 Add stability rework lab

---

## Decision 036: Reject Stability Rework Variants

Date:

- 2026-07-08

Decision:

- Reject all Mission 19 stability variants for live trading.

Reason:

- approved_count is 0
- best variant had 0 GO splits
- best variant reduced drawdown but produced negative average returns
- global verdict is REJECT_ALL_STABILITY_VARIANTS_NO_LIVE_TRADING

Verdict:

- REJECT_ALL
- LIVE_NO_GO

---

## Decision 037: Add Shared Indicator Engine

Date:

- 2026-07-08

Decision:

- Add reusable indicator engine for all future strategy labs.

Reason:

- Indicators should not be rewritten inside every strategy file.
- Future strategies need consistent SMA, EMA, ATR, RSI, ADX, Bollinger, Donchian, volatility, and percentile calculations.

Status:

- Active

Related commit:

- 7939c29 Add shared indicator engine

---

## Decision 038: Add Regime Kernel

Date:

- 2026-07-08

Decision:

- Add reusable regime classifier.

Reason:

- Mission 18 and Mission 19 showed that one strategy across all market conditions is weak.
- Future strategies must be tested inside market regimes.

Status:

- Active

Related commit:

- df58279 Add regime kernel

---

## Decision 039: Add Compression Breakout Lab

Date:

- 2026-07-08

Decision:

- Add compression breakout candidate lab as the first regime-aware institutional strategy test.

Reason:

- The system needs candidates that exploit specific market states.
- Compression breakout targets low-volatility compression followed by expansion.

Status:

- Active

Related commit:

- d8b0037 Add compression breakout lab

---

## Decision 040: Reject Mission 20 Compression Breakout Variants

Date:

- 2026-07-08

Decision:

- Reject all Mission 20 compression breakout variants for live trading.

Reason:

- approved_count is 0
- best variant had 0 GO splits
- total trades were only 1
- average Sharpe was negative
- global verdict is REJECT_ALL_COMPRESSION_BREAKOUT_VARIANTS_NO_LIVE_TRADING

Verdict:

- REJECT_ALL
- LIVE_NO_GO

---

## Decision 041: Add Volatility-Targeted TSMOM Lab

Date:

- 2026-07-08

Decision:

- Add volatility-targeted time-series momentum candidate lab.

Reason:

- Prior moving-average variants failed stability.
- The system needs a more institutional trend-following candidate.
- VT-TSMOM uses multi-horizon momentum, volatility targeting, trend confirmation, and regime filters.

Status:

- Active

Related commit:

- 8258dbf Add volatility targeted TSMOM lab

---

## Decision 042: Reject Mission 21 VT-TSMOM Variants

Date:

- 2026-07-08

Decision:

- Reject all Mission 21 VT-TSMOM variants for live trading.

Reason:

- approved_count is 0
- all variants had 0 GO splits
- all split verdicts were INSUFFICIENT_TRADES
- best variants generated 0 trades
- global verdict is REJECT_ALL_VT_TSMOM_VARIANTS_NO_LIVE_TRADING

Verdict:

- REJECT_ALL
- LIVE_NO_GO

---

## Decision 043: Add Funding / Basis Data Model

Date:

- 2026-07-08

Decision:

- Add data model for perpetual funding, mark prices, spot/perp basis, and delta-neutral research candidates.

Reason:

- Funding / basis arbitrage is the next crypto-native structural edge after VT-TSMOM.
- The system needs data tables before any strategy lab can be built.

Status:

- Active

Related commit:

- 40c7ae2 Add funding basis data model

---

## Decision 044: Keep Funding Strategy Research-Only

Date:

- 2026-07-08

Decision:

- Do not trade funding / basis signals yet.

Reason:

- Only synthetic demo data exists.
- Real funding-rate ingestion is not built.
- Liquidation, borrow cost, counterparty risk, and execution risk are not modeled.

Verdict:

- DATA_MODEL_GO
- LIVE_NO_GO

---

## Decision 045: Add Funding / Basis Ingestion

Date:

- 2026-07-08

Decision:

- Add public Binance Futures ingestion for funding history, mark price, index price, and open interest.

Reason:

- Mission 22 created the data model.
- Mission 23 must populate it with real public market data before any strategy test.

Status:

- Active

Related commit:

- 266f90d Add funding basis ingestion

---

## Decision 046: Funding Data Is Research-Only

Date:

- 2026-07-08

Decision:

- Keep funding / basis ingestion research-only.

Reason:

- Ingestion is not a strategy.
- Delta-neutral execution is not built.
- Risk models are incomplete.
- Liquidation, execution, borrow, and exchange-risk layers are missing.

Verdict:

- INGESTION_GO
- LIVE_NO_GO

---

## Decision 047: Add Delta-Neutral Funding Strategy Lab

Date:

- 2026-07-08

Decision:

- Add research-only strategy lab for delta-neutral funding candidates.

Reason:

- Mission 23 ingests real funding and basis data.
- The system needs a scoring layer before deeper backtesting.

Status:

- Active

Related commit:

- 2be3c61 Add delta neutral funding strategy lab

---

## Decision 048: Keep Delta-Neutral Funding Strategy Research-Only

Date:

- 2026-07-08

Decision:

- Do not trade delta-neutral funding signals.

Reason:

- No liquidation model.
- No exchange-risk model.
- No execution simulator.
- No position sizing engine.
- No risk governor.
- No private keys or signing.

Verdict:

- STRATEGY_LAB_GO
- LIVE_NO_GO

---

## Decision 049: Add Delta-Neutral Funding Backtest Engine

Date:

- 2026-07-08

Decision:

- Add research-only backtest engine for delta-neutral funding strategy.

Reason:

- Mission 24 produced a scoring layer only.
- The system needs simulated funding path returns, trade records, basis impact, cost assumptions, and result metrics.

Status:

- Active

Related commit:

- 0792bc8 Add delta neutral funding backtest engine

---

## Decision 050: Reject Current ETHUSDT Funding Backtest Candidate

Date:

- 2026-07-08

Decision:

- Reject current ETHUSDT delta-neutral funding candidate.

Reason:

- Backtest final verdict is NO_GO_LOW_AVG_FUNDING.
- Net return after execution cost is negative.
- Average annualized funding is below threshold.

Verdict:

- BACKTEST_ENGINE_GO
- CURRENT_CANDIDATE_NO_GO
- LIVE_NO_GO

---

## Decision 051: Add Funding Walk-Forward Validation

Date:

- 2026-07-08

Decision:

- Add research-only walk-forward validation for funding strategy variants.

Reason:

- Mission 25 created a backtest engine.
- Funding strategy needs split-level stability validation before any deeper risk work.

Status:

- Active

Related commit:

- b929c20 Add funding walk forward validation

---

## Decision 052: Keep Walk-Forward Funding Validation Research-Only

Date:

- 2026-07-08

Decision:

- Do not use walk-forward funding validation results for live trading.

Reason:

- No liquidation model.
- No leverage model.
- No exchange-risk model.
- No risk governor.
- No capital allocation engine.
- No private keys or signing.

Verdict:

- WALK_FORWARD_ENGINE_GO
- LIVE_NO_GO

---

## Decision 053: Add Liquidation + Leverage Risk Model

Date:

- 2026-07-08

Decision:

- Add research-only liquidation and leverage risk model for delta-neutral funding strategies.

Reason:

- Funding strategy cannot be promoted without liquidation distance, stress buffer, leverage safety, funding reversal, and basis shock checks.

Status:

- Active

Related commit:

- 8558405 Add liquidation leverage risk model

---

## Decision 054: Keep Leverage Risk Model Research-Only

Date:

- 2026-07-08

Decision:

- Do not use leverage risk results for live trading.

Reason:

- No live execution layer.
- No capital allocation engine.
- No risk governor.
- No exchange-risk model.
- No private keys or signing.

Verdict:

- RISK_MODEL_GO
- LIVE_NO_GO

---

## Decision 055: Add Execution Cost + Slippage Simulator

Date:

- 2026-07-08

Decision:

- Add research-only execution cost and slippage simulator.

Reason:

- Funding edge must survive realistic cost assumptions before multi-symbol scanning or paper trading.

Status:

- Active

Related commit:

- d85a533 Add execution cost slippage simulator

---

## Decision 056: Keep Execution Cost Model Research-Only

Date:

- 2026-07-08

Decision:

- Do not treat simulated execution-cost results as live execution approval.

Reason:

- No live order book.
- No broker/exchange fill engine.
- No execution gateway.
- No risk governor.
- No private keys or signing.

Verdict:

- COST_MODEL_GO
- LIVE_NO_GO

---

## Decision 057: Add Multi-Symbol Funding Scanner

Date:

- 2026-07-08

Decision:

- Add research-only scanner across multiple Binance USD-M perpetual symbols.

Reason:

- Single-symbol ETHUSDT testing produced weak funding edge.
- The system needs broader opportunity discovery before candidate ranking and paper trading.

Status:

- Active

Related commit:

- 82808d2 Add multi symbol funding scanner

---

## Decision 058: Keep Multi-Symbol Scanner Research-Only

Date:

- 2026-07-08

Decision:

- Do not trade scanner outputs.

Reason:

- Scanner output is only candidate discovery.
- No paper trading engine yet.
- No risk governor.
- No execution gateway.
- No private keys or signing.

Verdict:

- SCANNER_GO
- LIVE_NO_GO

---

## Decision 059: Add Candidate Ranking Engine

Date:

- 2026-07-08

Decision:

- Add research-only candidate ranking engine.

Reason:

- Multi-symbol scanner output needs second-level ranking before paper trading.
- Ranking must aggregate scanner score, funding edge, liquidity, risk gates, execution cost, and rejection reasons.

Status:

- Active

Related commit:

- c51213b Add candidate ranking engine

---

## Decision 060: Keep Candidate Ranking Research-Only

Date:

- 2026-07-08

Decision:

- Do not trade ranked candidates.

Reason:

- Ranking is only candidate selection.
- No paper trading engine yet.
- No capital allocation engine.
- No risk governor.
- No execution gateway.
- No private keys or signing.

Verdict:

- RANKING_ENGINE_GO
- LIVE_NO_GO

---

## Decision 061: Add Paper Trading Engine

Date:

- 2026-07-08

Decision:

- Add research-only paper trading engine.

Reason:

- Candidate ranking must be tested through simulated positions, simulated PnL, equity curve, and paper-trading gates before dashboarding or alerts.

Status:

- Active

Related commit:

- 93bb586 Add paper trading engine

---

## Decision 062: Keep Paper Trading Separate From Live Trading

Date:

- 2026-07-08

Decision:

- Paper trading results cannot trigger real trades.

Reason:

- No exchange gateway.
- No live order book.
- No capital allocation governor.
- No risk governor.
- No private keys or signing.

Verdict:

- PAPER_ENGINE_GO
- LIVE_NO_GO

---

## Decision 063: Add AI Learning Dataset + Model Registry

Date:

- 2026-07-08

Decision:

- Add research-only AI learning dataset and model registry.

Reason:

- DeltaGrid needs a safe foundation for learning from historical scanner, ranking, and paper-trading outcomes.

Status:

- Active

Related commit:

- 7889067 Add AI learning dataset registry

---

## Decision 064: AI Cannot Trade Or Override Risk

Date:

- 2026-07-08

Decision:

- AI outputs are limited to scoring, classification, labels, and recommendations.

Reason:

- Autonomous retraining and live execution are unsafe without strict validation, paper-trading gates, risk governors, and human approval.

Verdict:

- AI_LEARNING_GO
- AI_LIVE_TRADING_NO_GO

---

## Decision 065: Add Research Dashboard + Alerts

Date:

- 2026-07-08

Decision:

- Add research-only dashboard snapshots, alerts, and daily markdown reports.

Reason:

- DeltaGrid needs a single system status layer before scheduling, monitoring, or alert automation.

Status:

- Active

Related commit:

- fe0d65a Add research dashboard alerts

---

## Decision 066: Alerts Are Research-Only

Date:

- 2026-07-08

Decision:

- Alerts cannot trigger real trades.

Reason:

- No exchange gateway.
- No risk governor.
- No capital allocation engine.
- No private keys or signing.

Verdict:

- DASHBOARD_ALERTS_GO
- LIVE_NO_GO

## Mission 33 Decision - Unified Free Shadow Research Runner

Decision: DeltaGrid will run Mission 33 as a free, local, zero-capital SHADOW_MODE research pipeline.

Fixed constraints:

- no live trading
- no private keys
- no signing
- no paid APIs
- no cloud dependency
- no real capital

The runner must produce a full research verdict before any future promotion discussion.

---

## Mission 34 Decision - Add Shadow Research Run History Inspector

Decision:

- Add a read-only SQLite history inspector for shadow research pipeline runs.

Reason:

- Mission 33 can generate shadow pipeline runs.
- DeltaGrid needs a safe way to inspect accumulated history before adding more automation.
- The system must preserve visibility into alerts, rejections, verdicts, stage counts, reports, and safety flags.

Files:

- offchain/backtest/research_run_history_inspector.py
- offchain/tests/test_research_run_history_inspector.py

Related code commit:

- 1937ebd Add shadow research run history inspector

Status:

- Active

Live trading:

- DISABLED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- real capital
- live trading

---

## Mission 35 Decision - Add Shadow Candidate Replay Harness

Decision:

- Add deterministic replay scenarios for shadow candidate research.

Reason:

- Mission 34 can inspect history.
- DeltaGrid now needs controlled replay scenarios to generate richer history safely.
- Replays must cover approvals, rejections, mixed quality, and approved-universe enforcement.

Files:

- offchain/backtest/shadow_candidate_replay_harness.py
- offchain/tests/test_shadow_candidate_replay_harness.py

Related code commit:

- 9b09f52 Add shadow candidate replay harness

Status:

- Active

Live trading:

- DISABLED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 36 Decision - Add Shadow Replay Performance Reporter

Decision:

- Add a performance-style reporter for shadow candidate replay results.

Reason:

- Mission 35 generates controlled replay scenarios.
- DeltaGrid needs a compact research report before adding more automation.
- Approval/rejection rates and safety breach counts must be visible.

Files:

- offchain/backtest/shadow_replay_performance_reporter.py
- offchain/tests/test_shadow_replay_performance_reporter.py

Related code commit:

- 36cb1fd Add shadow replay performance reporter

Status:

- Active

Live trading:

- DISABLED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 37 Decision - Add Shadow Research Decision Gate

Decision:

- Add a strict board-level gate for Mission 36 performance reports.

Reason:

- Mission 36 summarizes replay performance.
- DeltaGrid needs a formal go/no-go governance layer before future automation.
- The gate must block live trading and capital deployment regardless of shadow approval.

Files:

- offchain/backtest/shadow_research_decision_gate.py
- offchain/tests/test_shadow_research_decision_gate.py

Related code commit:

- 9616a4f Add shadow research decision gate

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 38 Decision - Add Shadow Paper Observation Ledger

Decision:

- Add a dedicated ledger for approved shadow-paper observations.

Reason:

- Mission 37 approved shadow-paper observation only.
- DeltaGrid needs auditable observation records before future automation.
- Every observation must be linked to a decision gate, performance report, replay label, and scenario.

Files:

- offchain/backtest/shadow_paper_observation_ledger.py
- offchain/tests/test_shadow_paper_observation_ledger.py

Related code commit:

- 07743ad Add shadow paper observation ledger

Status:

- Active

Live trading:

- DISABLED

Live order sent:

- false

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 39 Decision - Add Shadow Observation Lifecycle Manager

Decision:

- Add lifecycle tracking for open shadow-paper observations.

Reason:

- Mission 38 opened shadow observations.
- DeltaGrid needs age, funding-accrual, risk-status, and close-eligibility tracking.
- Open observations must remain auditable before any future outcome analysis.

Files:

- offchain/backtest/shadow_observation_lifecycle_manager.py
- offchain/tests/test_shadow_observation_lifecycle_manager.py

Related code commit:

- 8669899 Add shadow observation lifecycle manager

Status:

- Active

Live trading:

- DISABLED

Live order sent:

- 0

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 40 Decision - Add Shadow Observation PnL Attribution Engine

Decision:

- Add cost-aware PnL attribution for shadow observations.

Reason:

- Mission 39 tracks expected funding accrual.
- DeltaGrid needs to compare expected funding against fees, spread cost, and slippage cost.
- Young observations may show negative expected net PnL after costs, which is important for close timing and strategy evaluation.

Files:

- offchain/backtest/shadow_observation_pnl_attribution.py
- offchain/tests/test_shadow_observation_pnl_attribution.py

Related code commit:

- 34629c4 Add shadow observation PnL attribution engine

Status:

- Active

Live trading:

- DISABLED

Live order sent:

- 0

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 41 Decision - Add Local Mission Automation Harness

Decision:

- Add local mission automation to reduce repetitive verification work.

Reason:

- Missions now require repeated compile, test, report, and git checks.
- Local automation improves speed without introducing live-trading risk.
- Automation must remain development-only at this stage.

Files:

- scripts/__init__.py
- scripts/mission_control.py
- offchain/tests/test_mission_control.py

Related code commit:

- df295d1 Add local mission automation harness

Status:

- Active

Live trading:

- DISABLED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 42 Decision - Add One-Command Mission Pack Runner

Decision:

- Add local JSON mission pack execution.

Reason:

- Mission 41 automated verification but not file generation.
- Future missions should be reducible to one generated pack plus one local command.
- The system must still reject unsafe paths and forbidden content.

Files:

- scripts/mission_pack_runner.py
- offchain/tests/test_mission_pack_runner.py

Related code commit:

- 66898c0 Add one-command mission pack runner

Status:

- Active

Live trading:

- DISABLED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 43 Decision - Add Shadow Observation Break-Even Tracker

Decision:

- Add break-even timing estimates for open shadow observations.

Reason:

- Mission 40 showed negative expected net PnL after costs.
- The bot must know how long funding accrual needs to cover estimated costs.
- Break-even timing is required before close/continue decisions can become intelligent.

Files:

- offchain/backtest/shadow_observation_break_even_tracker.py
- offchain/tests/test_shadow_observation_break_even_tracker.py

Related code commit:

- f880dd4 Add shadow observation break-even tracker

Status:

- Active

Live trading:

- DISABLED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 44 Decision - Add Shadow Observation Close Eligibility Engine

Decision:

- Add a close eligibility layer for shadow observations.

Reason:

- Mission 43 estimates when observations reach break-even.
- DeltaGrid needs a formal decision layer to continue, close, reject, or review observations.
- This improves future outcome analysis without enabling live trading.

Files:

- offchain/backtest/shadow_observation_close_eligibility_engine.py
- offchain/tests/test_shadow_observation_close_eligibility_engine.py

Related code commit:

- 110723d Add shadow observation close eligibility engine

Status:

- Active

Live trading:

- DISABLED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 45 Decision - Add Shadow Observation Outcome Finalizer

Decision:

- Add final shadow outcome accounting for observation decisions.

Reason:

- Mission 44 decides close/continue/reject.
- DeltaGrid needs a durable final outcome table and report for downstream analytics.
- This improves the observation lifecycle without enabling live trading.

Files:

- offchain/backtest/shadow_observation_outcome_finalizer.py
- offchain/tests/test_shadow_observation_outcome_finalizer.py

Related code commit:

- 8987443 Add shadow observation outcome finalizer

Status:

- Active

Live trading:

- DISABLED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 46 Decision - Add Shadow Observation Outcome Analytics Dashboard

Decision:

- Add executive analytics for finalized shadow observation outcomes.

Reason:

- Mission 45 finalizes outcomes.
- DeltaGrid needs aggregate visibility before adding more strategy logic.
- Symbol-level outcome summaries improve governance and research prioritization.

Files:

- offchain/backtest/shadow_observation_outcome_analytics_dashboard.py
- offchain/tests/test_shadow_observation_outcome_analytics_dashboard.py

Related code commit:

- 6371bf1 Add shadow observation outcome analytics dashboard

Status:

- Active

Live trading:

- DISABLED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 47 Decision - Add Shadow Research Executive Daily Report

Decision:

- Add one board-level daily report across the shadow research pipeline.

Reason:

- The project now has multiple reports across replay, decision, lifecycle, PnL, break-even, close, outcome, and analytics layers.
- The bot needs one executive summary before more strategy logic is added.
- This improves governance without enabling live trading.

Files:

- offchain/backtest/shadow_research_executive_daily_report.py
- offchain/tests/test_shadow_research_executive_daily_report.py

Related code commit:

- f733a84 Add shadow research executive daily report

Status:

- Active

Live trading:

- DISABLED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 48 Decision - Add Shadow Research Promotion Readiness Gate

Decision:

- Add a formal promotion readiness gate after executive daily reporting.

Reason:

- Mission 47 proved executive reporting is clean.
- DeltaGrid needs a formal decision before moving from governance/reporting into real-market alpha engine development.
- This gate approves only alpha-engine buildout while continuing to block live trading and capital deployment.

Files:

- offchain/backtest/shadow_research_promotion_readiness_gate.py
- offchain/tests/test_shadow_research_promotion_readiness_gate.py

Related code commit:

- 1eaaa3d Add shadow research promotion readiness gate

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 49 Decision - Add Real Market Public Data Ingestion

Decision:

- Add a public-data ingestion layer for Binance USDS-M Futures market data.

Reason:

- Mission 48 approved only real-market alpha engine buildout.
- Profitability cannot be evaluated without real public market data.
- Funding, basis, spread, and volume are required for the alpha scanner.

Files:

- offchain/backtest/real_market_public_data_ingestion.py
- offchain/tests/test_real_market_public_data_ingestion.py

Related code commit:

- f6703de Add real market public data ingestion

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 50 Decision - Add Historical Public Funding and Basis Dataset Builder

Decision:

- Add a historical public funding and basis dataset builder.

Reason:

- Mission 49 proved public data ingestion works online.
- Profitability cannot be evaluated from a single snapshot.
- The alpha scanner needs funding persistence, basis levels, spread estimates, and per-symbol statistics.

Files:

- offchain/backtest/historical_public_funding_basis_dataset_builder.py
- offchain/tests/test_historical_public_funding_basis_dataset_builder.py

Related code commit:

- 1ea549f Add historical public funding and basis dataset builder

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 51 Decision - Add Funding and Basis Alpha Scanner

Decision:

- Add the first alpha scanner using historical public funding and basis data.

Reason:

- Mission 50 produced a real historical dataset.
- DeltaGrid needs candidate ranking before paper observation expansion.
- Cost-adjusted carry must be tested before any strategy promotion.

Files:

- offchain/backtest/funding_basis_alpha_scanner.py
- offchain/tests/test_funding_basis_alpha_scanner.py

Related code commit:

- 4c49417 Add funding and basis alpha scanner

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 52 Decision - Add Cost Calibration and Break-Even Sensitivity Engine

Decision:

- Add cost calibration and break-even sensitivity after the alpha scanner.

Reason:

- Mission 51 found no approved alpha candidates under conservative costs.
- BTC and ETH were watchlist-only because they were negative after cost.
- The system needs to know whether candidates can become positive under lower fees, lower slippage, tighter spreads, or longer holding durations.

Files:

- offchain/backtest/cost_calibration_break_even_sensitivity_engine.py
- offchain/tests/test_cost_calibration_break_even_sensitivity_engine.py

Related code commit:

- 0ea72bd Add cost calibration break-even sensitivity engine

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 53 Decision - Add Calibrated Shadow Observation Planner

Decision:

- Add a planner that converts Mission 52 calibrated positive scenarios into shadow observation plans.

Reason:

- Mission 52 identified BTCUSDT and ETHUSDT as viable only under lower-cost or longer-hold assumptions.
- The next safe step is not trading; it is planning shadow observation entries.
- SOLUSDT should remain excluded until average funding turns positive.

Files:

- offchain/backtest/calibrated_shadow_observation_planner.py
- offchain/tests/test_calibrated_shadow_observation_planner.py

Related code commit:

- 4e821a6 Add calibrated shadow observation planner

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 54 Decision - Add Shadow Plan-to-Ledger Bridge

Decision:

- Add a bridge that converts calibrated shadow observation plans into formal shadow ledger entries.

Reason:

- Mission 53 created BTCUSDT and ETHUSDT shadow observation plans.
- The next safe step is ledger tracking, not trading.
- Ledger entries allow observation lifecycle tracking without orders or capital.

Files:

- offchain/backtest/shadow_plan_to_ledger_bridge.py
- offchain/tests/test_shadow_plan_to_ledger_bridge.py

Related code commit:

- dd0590e Add shadow plan to ledger bridge

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 55 Decision - Add Shadow Ledger Tracking Updater

Decision:

- Add a tracker that updates formal shadow ledger entries using public market data.

Reason:

- Mission 54 created BTCUSDT and ETHUSDT shadow ledger entries.
- Those entries require time-based public-data tracking.
- The system must invalidate observations when funding weakens, spread widens, or expected remaining carry turns unattractive.

Files:

- offchain/backtest/shadow_ledger_tracking_updater.py
- offchain/tests/test_shadow_ledger_tracking_updater.py

Related code commit:

- 7af57c4 Add shadow ledger tracking updater

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 56 Decision - Add Shadow Tracking Performance Reporter

Decision:

- Add a reporter that summarizes shadow tracking performance from Mission 55 updates.

Reason:

- Mission 55 created active BTC/ETH tracking updates.
- DeltaGrid needs performance visibility before building alerts or promotion gates.
- Carry drift, latest funding, and spread health must be summarized before any future strategy escalation.

Files:

- offchain/backtest/shadow_tracking_performance_reporter.py
- offchain/tests/test_shadow_tracking_performance_reporter.py

Related code commit:

- f114cc7 Add shadow tracking performance reporter

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

---

## Mission 57 Decision - Add Shadow Tracking Alert and Invalidation Router

Decision:

- Add an alert and invalidation router based on Mission 56 performance reports.

Reason:

- Mission 56 showed strong BTC/ETH shadow tracking.
- DeltaGrid needs route decisions before building automation or recurring tracking.
- The router makes continuation, warning, invalidation, refresh-data, and safety-block decisions explicit.

Files:

- offchain/backtest/shadow_tracking_alert_invalidation_router.py
- offchain/tests/test_shadow_tracking_alert_invalidation_router.py

Related code commit:

- 37bb975 Add shadow tracking alert invalidation router

Status:

- Active

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Still forbidden:

- private key usage
- transaction signing
- exchange order placement
- paid APIs
- real capital
- live trading

## Mission 58 Decision - Build Shadow Research Control Plane

Decision:

- Increase mission size from small modules to larger platform milestones.
- Add a control plane that orchestrates the full shadow research cycle.
- Add a documentation registry to reduce future inconsistency.

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

## Mission 59 Decision - Add Multi-Strategy Research Factory

Decision:

- Add a research factory that evaluates multiple strategy families.

Reason:

- DeltaGrid should not depend on a single funding/basis hypothesis.
- A real trading firm needs a pipeline of competing strategies.
- Strategies must be scored, rejected, watchlisted, or shortlisted using consistent evidence.

Related code commit:

- 271e249

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 60 Decision - Add Data Quality and Regime Intelligence

Decision:

- Add a data quality and market-regime layer before strategy promotion review.

Reason:

- Strategy scores can be misleading when data is stale, noisy, thin, or regime-unsafe.
- Candidate promotion must be filtered by data confidence, volatility, spread, and market risk.
- A trading firm needs risk intelligence before promotion review.

Related code commit:

- 92494a4 Add data quality regime intelligence engine

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 61 Decision - Add Shadow Portfolio Simulator

Decision:

- Add a portfolio-level shadow simulator before promotion board review.

Reason:

- Candidate-level alpha scores are not enough.
- Research must survive portfolio construction.
- Concentration risk must be measured before any future paper trading or capital review.

Related code commit:

- 545fe15 Add shadow portfolio simulator

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

## Mission 62 Decision - Add Research Promotion Board

Decision:

- Add a board-style research promotion gate before paper sandbox work.

Reason:

- Portfolio readiness must be reviewed by evidence, not by raw alpha score.
- Governance is required before any simulated trading engine.
- Approval must be scoped narrowly to paper sandbox research only.

Related code commit:

- bf9acf6

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 63 Decision - Add Paper Trading Sandbox

Decision:

- Add a local paper-only execution sandbox after research board approval.

Reason:

- Board approval should lead to a simulated execution environment, not live trading.
- The system needs paper orders, simulated fills, positions, fees, and slippage before any risk-control expansion.
- Live trading must remain impossible at this stage.

Related code commit:

- c29c9c9 Add paper trading sandbox

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 64 Decision - Add Institutional Risk Control Layer

Decision:

- Add a hard institutional risk-control layer after the paper sandbox.

Reason:

- Paper sandbox sessions need formal risk checks before observation continues.
- Exposure, cost, diversification, and safety limits must be enforced by code.
- No future phase should proceed without institutional-style risk evidence.

Related code commit:

- 7d01993 Add institutional risk control layer

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

## Mission 65 Decision - Add Capital Readiness Review

Decision:

- Add a capital-readiness governance layer after institutional risk control.

Reason:

- Paper observation readiness must be separated from real-capital approval.
- The system needs formal evidence before longer paper monitoring.
- Capital deployment must remain blocked until far stricter future gates exist.

Related code commit:

- b216235

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 66 Decision - Add Paper Observation Performance Monitor

Decision:

- Add paper-only performance monitoring after capital readiness review.

Reason:

- Extended paper observation needs position-level monitoring.
- Paper PnL, fee drag, and loss thresholds must be tracked before future risk expansion.
- Monitoring must remain local and paper-only.

Related code commit:

- 12dc48a Add paper observation performance monitor

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 67 Decision - Add Paper Drawdown Kill Switch

Decision:

- Add a paper-only drawdown kill switch after paper performance monitoring.

Reason:

- Extended paper observation needs hard stop-review thresholds.
- Paper drawdown and position-level losses must be controlled before future observation expansion.
- Kill-switch logic must remain local and paper-only.

Related code commit:

- e733e19 Add paper drawdown kill switch

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 68 Decision - Add Paper Recovery Stability Monitor

Decision:

- Add a paper-only recovery stability monitor after the drawdown kill switch.

Reason:

- Paper observation should continue only when the armed kill switch remains stable.
- Recovery stability needs explicit evidence before multi-cycle paper tracking.
- Stability monitoring must remain local and paper-only.

Related code commit:

- e25afdc Add paper recovery stability monitor

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 69 Decision - Add Multi-Cycle Paper Observation Tracker

Decision:

- Add a paper-only multi-cycle tracker after recovery stability monitoring.

Reason:

- AI outcome learning requires structured multi-cycle evidence.
- Paper observation continuation needs cumulative and cycle-level checks.
- Multi-cycle tracking must remain local and paper-only.

Related code commit:

- d5279a9 Add multi-cycle paper observation tracker

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

---

## Mission 70 Decision - Add AI Paper Outcome Learning Engine

Decision:

- Add a local deterministic AI paper-outcome learning layer after multi-cycle paper tracking.

Reason:

- Multi-cycle paper evidence should be converted into structured AI-learning features and labels.
- AI outputs must remain recommendation-only until much stricter future gates exist.
- The system must keep no-live-trading and no-real-capital safety boundaries.

Related code commit:

- e20c187 Add AI paper outcome learning engine

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 71 Decision - Add AI Feature Quality and Drift Guard

Decision:

- Add a local AI feature quality and drift guard after AI paper outcome learning.

Reason:

- AI datasets must not expand if feature quality is invalid.
- Feature drift must be visible before later AI learning stages.
- AI recommendations must remain non-autonomous and paper-only.

Related code commit:

- 7a7761b Add AI feature quality drift guard

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 72 Decision - Add AI Paper Dataset Expansion Scheduler

Decision:

- Add a controlled paper-only AI dataset expansion scheduler after AI feature quality approval.

Reason:

- AI learning needs more paper cycles, but expansion must be scheduled and bounded.
- Dataset growth must remain paper-only and guarded by feature quality checks.
- No autonomous execution should be introduced.

Related code commit:

- dfbdb86 Add AI paper dataset expansion scheduler

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 73 Decision - Add AI Outcome Dataset Builder Pack

Decision:

- Add a larger paper-only AI outcome dataset builder after dataset expansion scheduling.

Reason:

- Scheduled paper dataset items need to become structured dataset rows.
- Dataset rows must preserve full lineage and remain pending until paper outcomes are collected.
- Feature-store handoff should exist before training dataset registration.

Related code commit:

- f08169b Add AI outcome dataset builder pack

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 74 Decision - Add AI Feature Store and Training Dataset Registry

Decision:

- Add a local feature-store and training dataset registry after Mission 73 dataset row construction.

Reason:

- Dataset rows need feature-store registration before future outcome collection and training dataset activation.
- Training must remain locked until paper outcomes are collected and labels are finalized.
- The system must preserve no-live-trading and no-autonomous-training boundaries.

Related code commit:

- 9a40c11 Add AI feature store training dataset registry

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Model training:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 75 Decision - Add AI Paper Outcome Collection and Label Finalizer

Decision:

- Add a local paper-only outcome collection and label finalization layer after Mission 74 registry lock.

Reason:

- Pending outcome labels need to become finalized labels before label-quality checks.
- Training must remain locked even after labels are finalized.
- The system must preserve no-live-trading, no-training, and no-autonomous-trading boundaries.

Related code commit:

- d596cc9 Add AI paper outcome label finalizer

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Model training:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 76 Decision - Add AI Label Quality and Leakage Guard

Decision:

- Add a local label quality and leakage guard after Mission 75 label finalization.

Reason:

- Finalized labels must be validated before offline evaluation.
- Leakage checks must run before any evaluation or model-facing step.
- Training remains locked.

Related code commit:

- 1adadce Add AI label quality leakage guard

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Model training:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 78 Decision - Add AI Offline Evaluation Governance Board

Decision:

- Add a governance board after Mission 77 offline evaluation.

Reason:

- Offline evaluation evidence must be reviewed before research-only recommendations.
- The board must explicitly preserve no-live-trading, no-training, and no-autonomous-trading boundaries.
- Baseline accuracy must not be treated as profitability evidence.

Related code commit:

- 7e6426e Add AI offline evaluation governance board

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Model training:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 79 Decision - Add AI Research Recommendation Engine

Decision:

- Add a research-only recommendation engine after Mission 78 governance approval.

Reason:

- Governance-approved offline evidence must be translated into research-only recommendations.
- Recommendations must not become trade signals.
- Human review must remain mandatory.

Related code commit:

- cc49ec5 Add AI research recommendation engine

Live trading:

- BLOCKED

Capital deployment:

- BLOCKED

Model training:

- BLOCKED

Live signals:

- BLOCKED

Autonomous trading:

- BLOCKED

---

## Mission 80 Decision - Replace Human Approval Gate with Autonomous Policy Gate

Decision:

- Do not continue with a permanent Human Approval Gate.
- Add an Autonomous Policy Gate instead.

Reason:

- The project objective is a fully AI-integrated autonomous trading bot with self-learning capabilities.
- Human approval before every action would weaken the autonomous system objective.
- A machine-checkable policy gate preserves autonomy while keeping hard safety boundaries.

Approved by policy:

- autonomous paper-only progression

Not approved:

- live trading
- capital deployment
- model training
- live signal generation
- exchange execution
- private key access
- autonomous live strategy reweighting

---

## Mission 81 Decision - Add Autonomous Paper Signal Engine

Decision:

- Add an autonomous paper-only signal engine after Mission 80 policy approval.

Reason:

- DeltaGrid needs a controlled autonomous step after policy approval.
- The system should generate paper-only records before any paper execution agent exists.
- Signals must remain observe-only and must not become live trading signals.

Approved:

- paper-only observe signals
- handoff to Mission 82 Paper Execution Agent

Not approved:

- live trading
- capital deployment
- model training
- live signal generation
- exchange execution
- private key access
- autonomous live strategy reweighting

---

## Roadmap Decision After Mission 81

Decision:

- Add a full autonomous bot roadmap document.
- Keep Mission 82 as the next build target.
- Define live-market paper trading as a later milestone, not the immediate next step.
- Keep real-money live trading explicitly unapproved.

Reason:

- The project goal is a fully AI-integrated autonomous self-learning trading bot.
- The system needs a visible staged roadmap from paper execution to live-market paper trading.
- Safety gates must remain explicit.

Roadmap file:

- docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md

---

## Mission 82 Decision - Add Paper Execution Agent

Decision:

- Add a paper execution agent after Mission 81 paper-only signal generation.

Reason:

- DeltaGrid needs controlled execution evidence before it can learn from paper outcomes.
- Paper execution records create a bridge between paper signals and the self-learning feedback loop.
- The system must remain no-order and no-capital at this stage.

Approved:

- paper execution records
- handoff to Mission 83 Self-Learning Feedback Loop

Not approved:

- live trading
- capital deployment
- model training
- live signal generation
- exchange execution
- private key access
- autonomous live strategy reweighting

---

## Mission 83 Decision - Add Self-Learning Feedback Loop

Decision:

- Add a self-learning feedback loop after Mission 82 paper execution records.

Reason:

- DeltaGrid needs feedback evidence before offline training can be introduced.
- Feedback records create a bridge between paper execution and future offline training.
- The system must not train models or reweight strategies in Mission 83.

Approved:

- feedback record creation
- handoff to Mission 84 Offline Model Training Harness

Not approved:

- model training
- strategy reweighting
- live trading
- capital deployment
- live signal generation
- exchange execution
- private key access

---

## Mission 84 Decision - Add Offline Model Training Harness

Decision:

- Add an offline model training harness after Mission 83 feedback records.

Reason:

- DeltaGrid needs a safe offline-training boundary before any model promotion logic.
- Current feedback evidence is insufficient for actual model fitting.
- The harness must record locked training candidates without creating deployable artifacts.

Approved:

- offline training harness records
- locked training candidate records
- handoff to Mission 85 Model Promotion Engine review

Not approved:

- actual training on insufficient data
- model artifact creation
- model deployment
- live deployment
- strategy reweighting
- live trading
- capital deployment
- live signal generation
- exchange execution
- private key access
