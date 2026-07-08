# DeltaGrid Change Log

This file records completed project work.

---

## 2026-07-07

### Added: Smart Contract Foundation

Files:

- contracts/src/DeltaGridRegistry.sol
- contracts/src/DeltaGridRiskGuard.sol
- contracts/src/DeltaGridExecutor.sol
- contracts/src/MockOracle.sol
- contracts/test/DeltaGrid.t.sol
- contracts/foundry.toml
- contracts/remappings.txt

Verified:

- 6 Solidity tests passed
- 0 failed

Commit:

- 33d66e0 Complete DeltaGrid smart contract foundation

---

### Added: Safe Offchain Chain Monitor

Files:

- offchain/indexer/chain_monitor.py
- offchain/config/.env.example
- offchain/requirements.txt

Capabilities:

- loads environment config
- connects to Base Sepolia
- reads chain ID
- reads latest block
- reads gas price
- stores logs in SQLite
- uses no private keys
- signs no transactions

Verified:

- connected to chain_id=84532
- logged blocks successfully
- verified SQLite rows

Commit:

- 571044c Add safe offchain chain monitor

---

### Added: Source of Truth Documentation

Files:

- docs/PROJECT_SOURCE_OF_TRUTH.md
- docs/ADR/ADR-0001-safe-offchain-monitor.md
- docs/ADR/ADR-0002-git-commit-discipline.md
- docs/CHANGELOG.md
- docs/DECISION_LOG.md

Purpose:

- prevent drift
- document decisions
- track pivots
- track architecture
- track environment setup
- track Git discipline

Commit:

- pending

---

## Changelog Rules

Every mission must record:

- date
- files changed
- commands used
- verification result
- commit hash
- notes


---

## 2026-07-07

### Added: Local Profit Simulator and Risk Engine

Files:

- offchain/risk/__init__.py
- offchain/risk/risk_engine.py
- offchain/simulator/__init__.py
- offchain/simulator/profit_simulator.py
- offchain/tests/__init__.py
- offchain/tests/test_risk_engine.py

Capabilities:

- calculates gross profit
- calculates gas cost
- calculates flash-loan fee
- calculates slippage cost
- calculates total cost
- calculates net profit
- assigns risk score
- approves or rejects simulated trades
- stores simulation results in SQLite
- stores rejection reasons as JSON

Verified:

- 4 Python unit tests passed
- simulator ran successfully
- SQLite simulation_logs table received rows
- safe_trade approved correctly
- bad_cost_trade rejected correctly
- high_slippage_trade rejected correctly
- low_confidence_trade rejected correctly

Commit:

- 691cde4 Add local profit simulator and risk engine

Safety:

- no private keys
- no signing
- no real trades
- no real capital


---

## 2026-07-07

### Added: Market Data Schema and Opportunity Store

Files:

- offchain/db/__init__.py
- offchain/db/schema.py
- offchain/db/opportunity_store_demo.py
- offchain/tests/test_market_schema.py

Capabilities:

- creates schema_migrations table
- creates chains table
- creates blocks table
- creates gas_snapshots table
- creates tokens table
- creates pools table
- creates simulated_opportunities table
- creates risk_decisions table
- inserts demo chain
- inserts demo block
- inserts demo gas snapshot
- inserts demo tokens
- inserts demo pool
- inserts demo simulated opportunity
- inserts demo risk decision

Verified database counts:

- chains 1
- blocks 1
- gas_snapshots 1
- tokens 2
- pools 1
- simulated_opportunities 1
- risk_decisions 1

Verified latest opportunity:

- demo_arbitrage
- chain_id 84532
- block_number 43829863
- net_profit_wei 3000000000000000

Verified latest risk decision:

- risk_score 100
- approved 1
- reasons_json []

Commit:

- 3d75dc6 Add market data schema and opportunity store

Safety:

- no private keys
- no signing
- no real trades
- no real capital


---

## 2026-07-07

### Added: Chain Monitor Market Schema Integration

Files:

- offchain/indexer/__init__.py
- offchain/indexer/chain_monitor.py
- offchain/tests/test_chain_monitor_schema_integration.py

Capabilities:

- monitor now writes to block_logs
- monitor now writes to chains
- monitor now writes to blocks
- monitor now writes to gas_snapshots
- supports --once mode
- preserves safe read-only behavior

Verified:

- 8 Python tests passed
- live monitor connected to chain_id 84532
- latest live block stored: 43831432
- gas stored: 6000000
- block_logs count: 5
- chains count: 1
- blocks count: 2
- gas_snapshots count: 2

Commit:

- 4737dca Connect chain monitor to market schema

Safety:

- no private keys
- no signing
- no trades
- no real capital


---

## 2026-07-07

### Added: Token and Pool Seed Registry

Files:

- offchain/config/seed_tokens.json
- offchain/config/seed_pools.json
- offchain/db/seed_registry.py
- offchain/tests/test_seed_registry.py

Capabilities:

- loads token seed data
- loads pool seed data
- upserts chains
- upserts tokens
- upserts pools
- supports idempotent seeding

Verified:

- chains 1
- tokens 3
- pools 2

Seeded tokens:

- WETH
- USDC_DEMO
- DAI_DEMO

Seeded pools:

- demo-uniswap-v3 WETH/USDC_DEMO
- demo-uniswap-v3 USDC_DEMO/DAI_DEMO

Commit:

- 16e6824 Add token and pool seed registry

Safety:

- no private keys
- no signing
- no trades
- no real capital


---

## 2026-07-07

### Added: Pool Price Snapshot Simulator

Files:

- offchain/db/schema.py
- offchain/simulator/price_snapshot_simulator.py
- offchain/tests/test_price_snapshot_simulator.py

Capabilities:

- adds pool_price_snapshots table
- reads seeded pools
- generates local simulated prices
- stores token1/token0 price
- stores token0/token1 price
- stores liquidity score
- stores source as local_simulator
- attaches optional block number

Verified:

- pools 2
- pool_price_snapshots 2

Latest snapshots:

- WETH/USDC_DEMO price_token1_per_token0 3000
- USDC_DEMO/DAI_DEMO price_token1_per_token0 1

Commit:

- c4bcbfd Add pool price snapshot simulator

Safety:

- no private keys
- no signing
- no trades
- no real capital


---

## 2026-07-07

### Added: Local Route Builder

Files:

- offchain/db/schema.py
- offchain/simulator/route_builder.py
- offchain/tests/test_route_builder.py

Capabilities:

- adds route_candidates table
- reads latest pool price snapshots
- builds two-hop routes
- stores route candidates
- stores estimated output per input
- stores minimum liquidity score
- stores route JSON
- stores source as local_route_builder
- attaches block number

Verified:

- 13 Python tests passed
- pool_price_snapshots 2
- route_candidates 2

Routes created:

- WETH to DAI_DEMO
- DAI_DEMO to WETH

Commit:

- e73b359 Add local route builder

Safety:

- no private keys
- no signing
- no trades
- no real capital


---

## 2026-07-07

### Added: Historical Data and Backtest Framework

Files:

- offchain/db/schema.py
- offchain/backtest/__init__.py
- offchain/backtest/historical_data.py
- offchain/backtest/metrics.py
- offchain/backtest/backtest_engine.py
- offchain/tests/test_backtest_framework.py

Capabilities:

- stores historical candles
- stores backtest runs
- stores backtest trades
- generates synthetic multi-regime data
- runs MA crossover baseline backtest
- calculates net return
- calculates max drawdown
- calculates Sharpe ratio
- calculates profit factor
- calculates win rate
- includes fee assumptions
- includes slippage assumptions

Verified latest backtest:

- strategy ma_crossover_baseline
- version v1
- symbol WETH_USDC_DEMO
- net_return_pct -42.47
- max_drawdown_pct 55.30
- sharpe_ratio -1.44
- profit_factor 0.42
- win_rate_pct 29.41
- trades_count 17
- status research_only

Commit:

- 7b863f5 Add historical data and backtest framework

Recommendation:

- Framework GO
- MA crossover strategy NO-GO

Safety:

- no private keys
- no signing
- no real trades
- no real capital


---

## 2026-07-07

### Added: Strategy Metrics and Regime Analysis

Files:

- offchain/db/schema.py
- offchain/backtest/regime_analysis.py
- offchain/tests/test_regime_analysis.py

Capabilities:

- labels historical candles by market regime
- classifies bull, bear, and sideways regimes
- classifies high-volatility and low-volatility regimes
- stores market_regime_labels
- stores strategy_regime_metrics
- evaluates strategy performance by regime
- generates GO / NO_GO / INSUFFICIENT_SAMPLE verdicts

Verified:

- market_regime_labels 720
- strategy_regime_metrics 5

Latest regime results:

- bull: net PnL 1401.95, verdict NO_GO
- bear: net PnL -4002.04, verdict INSUFFICIENT_SAMPLE
- sideways: net PnL -1647.34, verdict NO_GO
- high_volatility: net PnL -369.74, verdict INSUFFICIENT_SAMPLE
- low_volatility: net PnL -3877.69, verdict NO_GO

Commit:

- 64644d1 Add strategy regime analysis

Recommendation:

- Regime analysis framework GO
- MA crossover strategy NO-GO
- Live trading NO-GO

Safety:

- no private keys
- no signing
- no real trades
- no real capital


---

## 2026-07-08

### Added: Optimized Opportunity Detector

Files:

- offchain/db/schema.py
- offchain/detector/__init__.py
- offchain/detector/opportunity_detector.py
- offchain/tests/test_opportunity_detector.py

Capabilities:

- reads route candidates
- classifies opportunity type
- rejects non-closed-loop routes
- calculates gross edge
- applies fee, slippage, gas, and safety buffer
- calculates net edge
- checks liquidity threshold
- assigns risk score
- stores rejection reasons
- stores assumptions
- keeps detector research-only

Verified:

- 20 tests passed
- routes_seen 2
- detections_created 2
- approved 0
- rejected 2

Current rejection reason:

- not_closed_loop_route

Commit:

- 3502dae Add optimized opportunity detector

Recommendation:

- Detector framework GO
- Current opportunities NO-GO
- Live trading NO-GO


---

## 2026-07-08

### Added: Closed-Loop Route Builder

Files:

- offchain/config/seed_pools.json
- offchain/simulator/price_snapshot_simulator.py
- offchain/simulator/closed_loop_route_builder.py
- offchain/tests/test_closed_loop_route_builder.py

Capabilities:

- adds third demo pool
- creates WETH to USDC to DAI to WETH route
- creates closed-loop route candidates
- sends closed-loop routes to opportunity detector
- validates profitable and unprofitable loops
- keeps all logic research-only

Verified:

- pools 3
- route_candidates 4
- opportunity_detections 6
- one closed-loop route approved
- one closed-loop route rejected

Approved route:

- multiplier 1.02000
- gross_edge_bps 200.00000
- total_cost_bps 50
- net_edge_bps 150.00000
- risk_score 88

Rejected route:

- multiplier 0.98039215686274509803921568627450980392156862745096
- reason gross_edge_not_positive
- reason net_edge_below_minimum

Commit:

- bb3ad35 Add closed-loop route builder

Recommendation:

- Closed-loop framework GO
- Live trading NO-GO


---

## 2026-07-08

### Added: Real Historical Market Data Ingestion

Files:

- offchain/backtest/binance_historical_data.py
- offchain/tests/test_binance_historical_data.py

Capabilities:

- fetches Binance Spot candles
- normalizes OHLCV data
- stores real candles in historical_candles
- supports real-data backtesting
- supports real-data regime analysis

Verified:

- 25 tests passed
- ETHUSDT candles ingested: 1277
- source: binance_spot
- timeframe: 1d

Backtest:

- net return: 30.77%
- max drawdown: 44.94%
- Sharpe: 0.388
- profit factor: 1.187
- win rate: 33.33%
- trades: 24

Recommendation:

- Data ingestion framework GO
- Strategy RESEARCH_ONLY
- Live trading NO-GO


---

## 2026-07-08

### Added: Strategy Validation Engine

Files:

- offchain/backtest/strategy_validation.py
- offchain/tests/test_strategy_validation.py

Verified:

- 28 tests passed
- ETHUSDT candles seen: 1277
- validation_results: 6
- walk-forward splits: 5
- GO_FOR_RESEARCH splits: 0

Full-period result:

- net return: 30.77%
- benchmark return: 30.44%
- excess return: 0.33%
- max drawdown: 44.94%
- Sharpe: 0.388
- profit factor: 1.187
- trades: 24

Verdict:

- NO_GO_DRAWDOWN_TOO_HIGH

Commit:

- 47ac51b Add strategy validation engine

Recommendation:

- Strategy validation framework GO
- MA crossover strategy NO-GO
- Live trading NO-GO


---

## 2026-07-08

### Added: Strategy Candidate Lab

Files:

- offchain/backtest/strategy_candidate_lab.py
- offchain/tests/test_strategy_candidate_lab.py

Capabilities:

- tests multiple strategy candidates
- compares each candidate against buy-and-hold
- ranks candidates using rank_score
- stores candidate results in SQLite
- rejects all candidates if none pass
- keeps global verdict research-only

Verified:

- 31 tests passed
- ETHUSDT candles seen: 1277
- candidate_results: 5
- approved_count: 0
- rejected_or_insufficient: 5

Best candidate:

- ma_crossover fast_20_slow_60

Best candidate result:

- net return: 96.21%
- benchmark return: 30.44%
- excess return: 65.77%
- max drawdown: 40.90%
- Sharpe: 0.676
- profit factor: 2.145
- trades: 12
- verdict: NO_GO_DRAWDOWN_TOO_HIGH

Global verdict:

- REJECT_ALL_NO_LIVE_TRADING

Commit:

- f7b06b9 Add strategy candidate lab

Recommendation:

- Candidate lab framework GO
- Best candidate WATCHLIST_ONLY
- Live trading NO-GO


---

## 2026-07-08

### Added: Drawdown Control Lab

Files:

- offchain/backtest/drawdown_control_lab.py
- offchain/tests/test_drawdown_control_lab.py

Capabilities:

- tests stop-loss controls
- tests trailing stop controls
- tests volatility filter
- tests drawdown guard
- tests cooldown logic
- stores results in SQLite

Verified:

- drawdown_control_results: 5
- approved_count: 0
- rejected_or_insufficient: 5

Best candidate:

- controlled_ma fast_20_slow_60_stop_12

Best result:

- net return: 113.87%
- benchmark return: 30.44%
- excess return: 83.43%
- max drawdown: 41.87%
- Sharpe: 0.740
- profit factor: 2.672
- trades: 14
- verdict: NO_GO_DRAWDOWN_TOO_HIGH

Lowest drawdown candidate:

- controlled_ma fast_20_slow_60_stop_10_trail_15_maxvol_85_ddguard_25_cooldown_20
- max drawdown: 26.69%
- verdict: NO_GO_UNDERPERFORMS_BENCHMARK

Global verdict:

- REJECT_ALL_NO_LIVE_TRADING

Commit:

- a74134e Add drawdown control lab

Recommendation:

- Drawdown control framework GO
- Strategy candidates NO-GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Walk-Forward Candidate Lab

Files:

- offchain/backtest/walk_forward_candidate_lab.py
- offchain/tests/test_walk_forward_candidate_lab.py

Capabilities:

- tests multiple candidates across walk-forward splits
- stores split-level results
- stores candidate summary results
- calculates GO split count
- calculates stability score
- rejects candidates that fail walk-forward validation

Verified:

- 37 tests passed
- ETHUSDT candles seen: 1277
- candidates tested: 7
- walk-forward splits: 5
- split_results: 35
- summary_results: 7
- approved_count: 0

Best candidate:

- ma_crossover fast_20_slow_60

Best candidate verdict:

- NO_GO_WALK_FORWARD_FAILURE

Global verdict:

- REJECT_ALL_NO_LIVE_TRADING

Commit:

- 0ef95c8 Add walk-forward candidate lab

Recommendation:

- Walk-forward framework GO
- Strategy candidates NO-GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Strategy Diagnostics and Failure Attribution

Files:

- offchain/backtest/strategy_diagnostics.py
- offchain/tests/test_strategy_diagnostics.py

Capabilities:

- loads walk-forward candidate summaries
- diagnoses why each candidate failed
- stores failure diagnostics in SQLite
- calculates severity score
- assigns primary failure
- recommends action per candidate

Verified:

- diagnostics: 7
- primary failure across all candidates: WEAK_WALK_FORWARD_STABILITY
- global verdict: DIAGNOSE_ONLY_NO_LIVE_TRADING

Highest severity candidate:

- ma_crossover fast_20_slow_60

Highest severity score:

- 165

Recommended action:

- REWORK_FOR_STABILITY

Commit:

- fd38244 Add strategy diagnostics

Recommendation:

- Diagnostics framework GO
- Strategy candidates NO-GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Stability Rework Lab

Files:

- offchain/backtest/stability_rework_lab.py
- offchain/tests/test_stability_rework_lab.py

Capabilities:

- tests stricter controlled MA variants
- adds volatility-gated variants
- adds drawdown-guarded variants
- adds cooldown-based variants
- stores split-level stability rework results
- stores summary-level stability rework results
- calculates consistency score
- recommends next action per variant

Verified:

- ETHUSDT candles seen: 1277
- variants tested: 5
- walk-forward splits: 5
- split_results: 25
- summary_results: 5
- approved_count: 0

Best variant:

- stability_controlled_ma fast_20_slow_100_stop_8_trail_12_vol55_dd20_cd20

Best variant verdict:

- NO_GO_STABILITY_FAILURE

Global verdict:

- REJECT_ALL_STABILITY_VARIANTS_NO_LIVE_TRADING

Commit:

- f93a531 Add stability rework lab

Recommendation:

- Stability rework framework GO
- Strategy variants NO-GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Mission 20 Regime Kernel and Compression Breakout Lab

Files:

- offchain/backtest/indicator_engine.py
- offchain/tests/test_indicator_engine.py
- offchain/backtest/regime_kernel.py
- offchain/tests/test_regime_kernel.py
- offchain/backtest/compression_breakout_lab.py
- offchain/tests/test_compression_breakout_lab.py

Capabilities:

- shared indicator engine
- reusable regime classification
- compression-to-expansion breakout candidate lab
- split-level compression breakout results
- summary-level compression breakout results
- stability scoring
- research-only global verdict

Verified:

- tests passed: 60
- ETHUSDT candles seen: 1277
- variants tested: 3
- walk-forward splits: 5
- split_results: 15
- summary_results: 3
- approved_count: 0

Best variant:

- compression_breakout donchian40_exit15_bb30_atr65_vol105_ema50

Best variant verdict:

- NO_GO_STABILITY_FAILURE

Global verdict:

- REJECT_ALL_COMPRESSION_BREAKOUT_VARIANTS_NO_LIVE_TRADING

Commits:

- 7939c29 Add shared indicator engine
- df58279 Add regime kernel
- d8b0037 Add compression breakout lab

Recommendation:

- Indicator engine GO
- Regime kernel GO
- Compression breakout framework GO
- Compression breakout variants NO-GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Volatility-Targeted Time-Series Momentum Lab

Files:

- offchain/backtest/vt_tsmom_lab.py
- offchain/tests/test_vt_tsmom_lab.py

Capabilities:

- multi-horizon momentum scoring
- EMA trend filter
- ADX trend confirmation
- ATR stop and trailing exit
- volatility-targeted position sizing
- regime-aware filtering
- split-level VT-TSMOM results
- summary-level VT-TSMOM results
- stability scoring
- research-only global verdict

Verified:

- ETHUSDT candles seen: 1277
- variants tested: 3
- walk-forward splits: 5
- split_results: 15
- summary_results: 3
- approved_count: 0

Best variant:

- vt_tsmom lb21_63_126_ema200_adx18_vol25_atr3

Best variant verdict:

- NO_GO_STABILITY_FAILURE

Global verdict:

- REJECT_ALL_VT_TSMOM_VARIANTS_NO_LIVE_TRADING

Split verdict finding:

- all splits were INSUFFICIENT_TRADES

Commit:

- 8258dbf Add volatility targeted TSMOM lab

Recommendation:

- VT-TSMOM framework GO
- VT-TSMOM variants NO-GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Funding / Basis Data Model

Files:

- offchain/backtest/funding_basis_model.py
- offchain/tests/test_funding_basis_model.py

Tables:

- funding_rates
- perp_mark_prices
- spot_perp_basis_snapshots
- delta_neutral_research_candidates

Capabilities:

- annualizes funding rates
- calculates spot/perp basis
- stores perpetual mark prices
- stores basis snapshots
- evaluates delta-neutral research candidates
- runs synthetic research-only demo seed

Commit:

- 40c7ae2 Add funding basis data model

Verdict:

- Data model GO
- Strategy NOT YET TESTED
- Live trading NO-GO

---

## 2026-07-08

### Added: Funding / Basis Ingestion

Files:

- offchain/backtest/funding_basis_ingestion.py
- offchain/tests/test_funding_basis_ingestion.py

Capabilities:

- fetches public Binance Futures funding history
- fetches public Binance Futures mark price and index price
- fetches public Binance Futures open interest
- writes funding rows into funding_rates
- writes mark/index/open-interest row into perp_mark_prices
- writes spot/perp basis snapshot
- writes delta-neutral research candidate
- writes ingestion audit row

Commit:

- 266f90d Add funding basis ingestion

Verdict:

- Public ingestion GO
- Strategy NOT YET TESTED
- Live trading NO-GO

---

## 2026-07-08

### Added: Delta-Neutral Funding Strategy Lab

Files:

- offchain/backtest/delta_neutral_funding_lab.py
- offchain/tests/test_delta_neutral_funding_lab.py

Tables:

- delta_neutral_funding_lab_results
- delta_neutral_funding_lab_summary

Capabilities:

- evaluates ingested funding history
- evaluates spot/perp basis
- applies basis penalty
- applies execution-cost assumption
- estimates expected annualized edge
- estimates stress edge
- estimates 30-day carry
- produces GO / NO-GO verdict
- records research-only summary

Commit:

- 2be3c61 Add delta neutral funding strategy lab

Verdict:

- Funding strategy lab GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Delta-Neutral Funding Backtest Engine

Files:

- offchain/backtest/delta_neutral_funding_backtest.py
- offchain/tests/test_delta_neutral_funding_backtest.py

Tables:

- delta_neutral_funding_backtest_trades
- delta_neutral_funding_backtest_results
- delta_neutral_funding_backtest_summary

Capabilities:

- simulates long spot / short perpetual funding carry
- accumulates funding path returns
- models basis entry and exit impact
- applies execution-cost assumption
- creates trade-level records
- creates result-level records
- creates summary-level records
- computes win rate, drawdown, profit factor, and net return
- produces research-only GO / NO-GO verdict

Mission 25 result:

- trades_created: 1
- final verdict: NO_GO_LOW_AVG_FUNDING
- global verdict: REJECT_DELTA_NEUTRAL_FUNDING_BACKTEST_NO_LIVE_TRADING

Commit:

- 0792bc8 Add delta neutral funding backtest engine

Verdict:

- Funding backtest engine GO
- Current ETHUSDT candidate NO-GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Funding Strategy Walk-Forward Validation

Files:

- offchain/backtest/funding_walk_forward_validation.py
- offchain/tests/test_funding_walk_forward_validation.py

Tables:

- funding_walk_forward_split_results
- funding_walk_forward_summary

Capabilities:

- builds walk-forward train/test funding splits
- evaluates multiple funding strategy parameter variants
- records split-level results
- records summary-level validation results
- computes stability score
- produces research-only GO / NO-GO verdict

Commit:

- b929c20 Add funding walk forward validation

Verdict:

- Funding walk-forward validation GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Liquidation + Leverage Risk Model

Files:

- offchain/backtest/liquidation_leverage_risk_model.py
- offchain/tests/test_liquidation_leverage_risk_model.py

Tables:

- liquidation_leverage_risk_results
- liquidation_leverage_risk_summary

Capabilities:

- computes short perpetual liquidation price
- computes liquidation buffer percentage
- applies adverse spot shock
- applies adverse basis shock
- computes stressed mark price
- computes post-stress liquidation buffer
- computes funding reversal loss
- computes execution cost
- estimates total stress loss
- estimates max safe leverage
- produces research-only GO / NO-GO verdict

Commit:

- 8558405 Add liquidation leverage risk model

Verdict:

- Liquidation + leverage risk model GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Execution Cost + Slippage Simulator

Files:

- offchain/backtest/execution_cost_slippage_simulator.py
- offchain/tests/test_execution_cost_slippage_simulator.py

Tables:

- execution_cost_slippage_results
- execution_cost_slippage_summary

Capabilities:

- computes spot and perpetual leg costs
- computes fee, spread, and slippage assumptions
- computes participation rate
- applies liquidity penalty
- computes combined round-trip cost
- computes expected funding edge
- computes net expected edge after costs
- computes edge-to-cost ratio
- produces research-only GO / NO-GO verdict

Commit:

- d85a533 Add execution cost slippage simulator

Verdict:

- Execution cost + slippage simulator GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Multi-Symbol Funding Scanner

Files:

- offchain/backtest/multi_symbol_funding_scanner.py
- offchain/tests/test_multi_symbol_funding_scanner.py

Tables:

- multi_symbol_funding_scan_results
- multi_symbol_funding_scan_summary

Capabilities:

- scans multiple perpetual symbols
- computes annualized funding
- computes basis
- estimates expected funding edge
- applies execution cost proxy
- computes net expected edge
- computes edge-to-cost ratio
- scores liquidity and funding strength
- penalizes basis risk
- ranks candidates
- produces research-only GO / NO-GO verdict

Commit:

- 82808d2 Add multi symbol funding scanner

Verdict:

- Multi-symbol funding scanner GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Candidate Ranking Engine

Files:

- offchain/backtest/candidate_ranking_engine.py
- offchain/tests/test_candidate_ranking_engine.py

Tables:

- candidate_ranking_results
- candidate_ranking_summary

Capabilities:

- loads multi-symbol funding scan results
- enriches candidates with walk-forward context
- enriches candidates with liquidation risk context
- enriches candidates with execution cost context
- computes composite ranking score
- aggregates rejection reasons
- ranks candidates across symbols
- produces research-only GO / NO-GO verdict

Commit:

- c51213b Add candidate ranking engine

Verdict:

- Candidate ranking engine GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Paper Trading Engine

Files:

- offchain/backtest/paper_trading_engine.py
- offchain/tests/test_paper_trading_engine.py

Tables:

- paper_trading_positions
- paper_trading_trades
- paper_trading_equity_curve
- paper_trading_summary

Capabilities:

- loads ranked candidates
- filters paper-trade eligible candidates
- creates simulated positions
- simulates long spot / short perpetual trades
- computes funding accrual
- subtracts execution cost
- computes paper PnL
- builds paper equity curve
- computes drawdown, win rate, and profit factor
- produces research-only GO / NO-GO paper verdict

Commit:

- 93bb586 Add paper trading engine

Verdict:

- Paper trading engine GO
- Live trading NO-GO

---

## 2026-07-08

### Added: AI Learning Dataset + Model Registry

Files:

- offchain/backtest/ai_learning_registry.py
- offchain/tests/test_ai_learning_registry.py

Tables:

- ai_learning_examples
- ai_model_registry

Capabilities:

- extracts learning examples from ranked candidates
- joins paper trading outcomes when available
- builds AI feature dictionaries
- builds training labels
- separates observation-only examples from training-eligible examples
- registers baseline model metadata
- rejects training when data is insufficient
- prevents paper/live approval by default

Commit:

- 7889067 Add AI learning dataset registry

Verdict:

- AI learning registry GO
- Live trading NO-GO

---

## 2026-07-08

### Added: Research Dashboard + Alerts

Files:

- offchain/backtest/research_dashboard_alerts.py
- offchain/tests/test_research_dashboard_alerts.py

Tables:

- research_dashboard_snapshots
- research_dashboard_alerts
- research_daily_reports

Capabilities:

- summarizes scanner output
- summarizes ranking output
- summarizes paper trading output
- summarizes AI model registry output
- generates research alerts
- generates blocking safety alerts
- writes local markdown research report
- stores dashboard snapshots and report records

Commit:

- fe0d65a Add research dashboard alerts

Verdict:

- Research dashboard + alerts GO
- Live trading NO-GO

## Mission 33 - Unified Free Shadow Research Runner

- Added a unified local shadow research pipeline runner.
- Added SQLite persistence for full pipeline runs, stage results, and markdown reports.
- Added safe default behavior that fails closed when no strong candidates exist.
- Added tests proving live trading remains disabled.
- Added ADR-0033 documentation.

---

## Mission 34 - Shadow Research Run History Inspector

Added:

- read-only inspector for Mission 33 shadow research pipeline history
- summary of run counts
- summary of verdict counts
- latest run and latest verdict inspection
- alert and blocking-alert inspection
- stage-count inspection
- report-length inspection
- live-trading safety verification across inspected runs

Files:

- offchain/backtest/research_run_history_inspector.py
- offchain/tests/test_research_run_history_inspector.py

Code commit:

- 1937ebd Add shadow research run history inspector

Safety:

- live trading remains disabled
- no private keys
- no signing
- no exchange orders
- no real capital

Verdict:

- Mission 34 observability GO
- Live trading NO-GO

---

## Mission 35 - Shadow Candidate Replay Harness

Added:

- deterministic replay harness for shadow candidate scenarios
- fail-closed baseline replay
- approved BTC shadow replay
- mixed approved/rejected replay
- non-universe rejection replay
- SQLite replay metadata tables
- tests for all replay paths

Files:

- offchain/backtest/shadow_candidate_replay_harness.py
- offchain/tests/test_shadow_candidate_replay_harness.py

Tables:

- shadow_candidate_replay_runs
- shadow_candidate_replay_scenarios

Code commit:

- 9b09f52 Add shadow candidate replay harness

Safety:

- live trading remains disabled
- no private keys
- no signing
- no exchange orders
- no paid APIs
- no real capital

Verdict:

- Mission 35 replay harness GO
- Live trading NO-GO

---

## Mission 36 - Shadow Replay Performance Reporter

Added:

- shadow replay performance reporter
- aggregate replay metrics
- approval rate
- rejection rate
- paper position rate
- live trading breach count
- scenario distribution
- scenario verdict counts
- markdown research report
- SQLite persistence for performance reports

Files:

- offchain/backtest/shadow_replay_performance_reporter.py
- offchain/tests/test_shadow_replay_performance_reporter.py

Tables:

- shadow_replay_performance_reports

Code commit:

- 36cb1fd Add shadow replay performance reporter

Safety:

- live trading remains disabled
- no private keys
- no signing
- no exchange orders
- no paid APIs
- no real capital

Verdict:

- Mission 36 performance reporting GO
- Live trading NO-GO
