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
