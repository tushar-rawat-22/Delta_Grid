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
