# DeltaGrid Project Source of Truth

## 1. Purpose

This file is the main memory document for DeltaGrid.

It exists to prevent:

- project drift
- silly iterations
- random feature changes
- unclear technical direction
- repeated rework
- accidental mixing with SkillMint
- premature real-money execution
- undocumented pivots
- unsafe private key usage

Rule:

Every major technical decision, architecture change, workflow change, environment change, dependency change, or pivot must be documented here or inside docs/ADR before implementation.

---

## 2. Project Identity

Project name:

- DeltaGrid

Project type:

- Research-first DeFi indexing, monitoring, simulation, execution, and risk-management platform.

Current phase:

- Local + testnet research only.

Current rule:

- No real capital.
- No mainnet deployment.
- No private key usage.
- No transaction signing.
- No live trading.

Correct positioning:

- DeltaGrid is not a money bot.
- DeltaGrid is a research-first DeFi execution and risk platform.
- The system must observe, simulate, validate, and pass promotion gates before execution.

---

## 3. Current Confirmed State

### 3.1 Smart Contract Foundation

Status:

- Complete
- Tested
- Committed

Files:

- contracts/src/DeltaGridRegistry.sol
- contracts/src/DeltaGridRiskGuard.sol
- contracts/src/DeltaGridExecutor.sol
- contracts/src/MockOracle.sol
- contracts/test/DeltaGrid.t.sol
- contracts/foundry.toml
- contracts/remappings.txt

Verified result:

- 6 Solidity tests passed
- 0 failed
- forge build successful
- forge test successful

Commit:

- 33d66e0 Complete DeltaGrid smart contract foundation

Purpose:

- Registry allowlists
- Risk guard checks
- Executor safety validation
- Mock oracle for testing
- Contract-level safety foundation

---

### 3.2 Safe Offchain Chain Monitor

Status:

- Complete
- Tested
- Committed

Files:

- offchain/indexer/chain_monitor.py
- offchain/config/.env.example
- offchain/requirements.txt

Runtime mode:

- Safe monitoring only
- No private keys
- No signing
- No real trades

Confirmed RPC:

- https://sepolia.base.org

Confirmed chain:

- Base Sepolia

Confirmed chain ID:

- 84532

Confirmed block logs:

- 43829854
- 43829857
- 43829860
- 43829863

Confirmed database example:

- ('2026-07-07T12:39:57.301908+00:00', 84532, 43829854, '6000000')

Commit:

- 571044c Add safe offchain chain monitor

Purpose:

- Prove RPC connectivity
- Prove Python environment works
- Prove SQLite logging works
- Create safe blockchain data foundation

---

## 4. Technical Decisions Already Made

| Area | Decision | Reason | Status |
|---|---|---|---|
| Project folder | Use ~/deltagrid | Keep separate from SkillMint | Active |
| Development phase | Local + testnet only | Avoid real capital risk | Active |
| Smart contracts | Use Foundry | Strong Solidity testing | Active |
| Offchain language | Use Python 3.12 | Good for indexing, data, simulation, risk | Active |
| Python isolation | Use offchain/.venv | Avoid dependency conflicts | Active |
| Dependencies | Use requirements.txt | Reproducible setup | Active |
| Config | Track .env.example, ignore .env | Prevent secrets leak | Active |
| Chain | Start with Base Sepolia | Safe testnet monitoring | Active |
| Database | Use SQLite locally | Simple local storage | Active |
| Git | Atomic commits | Clean history and rollback | Active |
| Staging | Selective git add | Avoid accidental commits | Active |
| Execution | No signing yet | Safety-first | Active |

---

## 5. Environment Setup

### 5.1 Python virtual environment

Location:

- offchain/.venv

Commands used:

    cd ~/deltagrid/offchain
    python3.12 -m venv .venv
    source .venv/bin/activate

Reason:

- Keeps DeltaGrid dependencies isolated.
- Prevents conflict with SkillMint.
- Prevents global Python pollution.

---

### 5.2 Dependencies

Installed packages:

- web3
- python-dotenv
- requests
- pandas
- pydantic
- sqlalchemy

Command used:

    python -m pip install web3 python-dotenv requests pandas pydantic sqlalchemy

Dependency snapshot command:

    python -m pip freeze > requirements.txt

Tracked dependency file:

- offchain/requirements.txt

Rule:

Whenever dependencies change, run:

    cd ~/deltagrid/offchain
    source .venv/bin/activate
    python -m pip freeze > requirements.txt

Then commit requirements.txt with the related code change.

---

## 6. Running the Offchain Monitor

Go to offchain folder:

    cd ~/deltagrid/offchain

Activate environment:

    source .venv/bin/activate

Run monitor:

    python indexer/chain_monitor.py

Expected output:

    DeltaGrid Chain Monitor
    Mode: safe monitoring only
    No private keys. No signing. No real trades.
    RPC: https://sepolia.base.org
    Connected to chain_id=84532

Stop:

    Control + C

---

## 7. Verify SQLite Logs

Run:

    cd ~/deltagrid/offchain
    source .venv/bin/activate

    python - <<'PYTHON'
    import sqlite3

    conn = sqlite3.connect("deltagrid.db")
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT timestamp_utc, chain_id, block_number, gas_price_wei
    FROM block_logs
    ORDER BY id DESC
    LIMIT 10
    """).fetchall()

    for row in rows:
        print(row)

    conn.close()
    PYTHON

Expected:

- Recent rows should show timestamp, chain_id, block number, and gas price.

---

## 8. Git Workflow

### 8.1 Current branch

Current branch:

- master

Do not rename yet unless needed.

---

### 8.2 Commit style

Use atomic commits.

Good examples:

    git commit -m "Complete DeltaGrid smart contract foundation"
    git commit -m "Add safe offchain chain monitor"
    git commit -m "Add risk scoring simulator"
    git commit -m "Document offchain environment setup"

Bad examples:

    git commit -m "update"
    git commit -m "changes"
    git commit -m "final"
    git commit -m "working"

---

### 8.3 Selective staging rule

Do not blindly use:

    git add .

Use selective staging:

    git add specific/file1 specific/file2 specific/file3

Actual command used for Mission 2:

    git add offchain/indexer/chain_monitor.py offchain/config/.env.example offchain/requirements.txt

Reason:

Selective staging prevents accidental commits of:

- .env
- .venv
- databases
- logs
- private keys
- cache files
- unrelated experiments

---

## 9. Directory Boundaries

### contracts/

Purpose:

- Solidity code
- Foundry tests
- Smart contract safety layer

Allowed:

- .sol contracts
- Foundry tests
- foundry.toml
- remappings.txt

Not allowed:

- Python indexers
- SQLite databases
- private keys
- live execution scripts without review

---

### offchain/indexer/

Purpose:

- Blockchain observation
- RPC polling
- Block logging
- Event indexing later

Current file:

- offchain/indexer/chain_monitor.py

Not allowed yet:

- trading
- signing
- private keys
- live execution

---

### offchain/config/

Purpose:

- Environment configuration

Tracked:

- offchain/config/.env.example

Not tracked:

- offchain/config/.env

Rule:

- Commit .env.example.
- Never commit .env.

---

### docs/

Purpose:

- Source of truth
- ADRs
- Decision logs
- Changelog
- Drift prevention

Rule:

- Every pivot must be documented.
- Every major technical decision needs an ADR.
- Every completed mission updates CHANGELOG.

---

## 10. Environment Configuration

Current .env.example:

    RPC_URL=https://sepolia.base.org
    POLL_SECONDS=5
    DB_PATH=deltagrid.db

Current variables:

| Variable | Purpose | Current value |
|---|---|---|
| RPC_URL | RPC endpoint | https://sepolia.base.org |
| POLL_SECONDS | Monitor polling interval | 5 |
| DB_PATH | SQLite database path | deltagrid.db |

Future variables may include:

- CHAIN_NAME
- CHAIN_ID
- LOG_LEVEL
- PRIMARY_RPC_URL
- FALLBACK_RPC_URL
- DATABASE_URL
- ALERT_WEBHOOK_URL

Private keys are not allowed in early phases.

---

## 11. Safety Rules

Current forbidden actions:

- No real capital
- No mainnet deployment
- No live private key usage
- No transaction signing
- No live trading
- No sandwiching
- No exploit-style MEV
- No public yield promises
- No automatic execution before simulation
- No mixing DeltaGrid with SkillMint

Current allowed actions:

- Compile contracts
- Run tests
- Monitor testnet blocks
- Log gas and block data
- Use SQLite locally
- Build local simulators
- Build risk scoring
- Write documentation

---

## 12. Promotion Gates

Gate 1:

- Local contracts compile
- Status: complete

Gate 2:

- Contract tests pass
- Status: complete

Gate 3:

- Offchain monitor runs safely
- Status: complete

Gate 4:

- Block and gas logs stored
- Status: complete

Gate 5:

- Local profit simulator works
- Status: next

Gate 6:

- Risk scoring engine works
- Status: next

Gate 7:

- Testnet-only simulation

Gate 8:

- Fork tests

Gate 9:

- Paper/demo validation

Gate 10:

- Tiny live-capital experiment

Gate 11:

- Scale only after evidence

---

## 13. Pivot Rules

A pivot must be documented before implementation if it changes:

- chain
- RPC provider
- database
- execution model
- risk model
- private key handling
- smart contract architecture
- indexing scope
- strategy logic
- simulation methodology
- deployment target
- capital usage

Pivot template:

    Date:
    Current approach:
    Problem:
    Proposed change:
    Why this is needed:
    Risks:
    Rollback plan:
    Approved:

---

## 14. Next Mission

Mission 3:

- Build local profit simulator
- Build risk scoring engine

Allowed directories:

- offchain/simulator/
- offchain/risk/
- docs/

Not allowed yet:

- mainnet deployment
- private key usage
- real transaction signing
- real capital
- live trading

Mission 3 success criteria:

- Gross profit can be calculated
- Gas cost can be included
- Flash-loan fee can be included
- Slippage cost can be included
- Net profit can be calculated
- Risk score can approve or reject a simulated trade
- All outputs are deterministic


---

# Mission 3 Completion Record

Date:

- 2026-07-07

Status:

- Complete
- Tested
- Committed

Commit:

- 691cde4 Add local profit simulator and risk engine

Files:

- offchain/risk/__init__.py
- offchain/risk/risk_engine.py
- offchain/simulator/__init__.py
- offchain/simulator/profit_simulator.py
- offchain/tests/__init__.py
- offchain/tests/test_risk_engine.py

Verified:

- 4 unit tests passed
- local simulator ran successfully
- simulation_logs table received records
- approved and rejected scenarios behaved correctly

Completed gates:

- Gate 5: Local profit simulator works
- Gate 6: Risk scoring engine works

Next gate:

- Gate 7: Testnet-only simulation

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 4 Completion Record

Date:

- 2026-07-07

Status:

- Complete
- Verified
- Committed

Commit:

- 3d75dc6 Add market data schema and opportunity store

Files:

- offchain/db/__init__.py
- offchain/db/schema.py
- offchain/db/opportunity_store_demo.py
- offchain/tests/test_market_schema.py

Database tables added:

- schema_migrations
- chains
- blocks
- gas_snapshots
- tokens
- pools
- simulated_opportunities
- risk_decisions

Verified database counts:

- chains 1
- blocks 1
- gas_snapshots 1
- tokens 2
- pools 1
- simulated_opportunities 1
- risk_decisions 1

Verified opportunity:

- demo_arbitrage
- chain_id 84532
- block_number 43829863
- net_profit_wei 3000000000000000

Verified risk decision:

- risk_score 100
- approved 1
- reasons_json []

Completed foundation:

- Market data schema
- Opportunity store
- Risk decision store

Next recommended mission:

- Mission 5: Connect chain monitor to market database schema

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 5 Completion Record

Date:

- 2026-07-07

Status:

- Complete
- Tested
- Live monitor verified
- Committed

Commit:

- 4737dca Connect chain monitor to market schema

Files:

- offchain/indexer/__init__.py
- offchain/indexer/chain_monitor.py
- offchain/tests/test_chain_monitor_schema_integration.py

Verified tests:

- 8 Python tests passed

Verified live monitor:

- chain_id 84532
- block_number 43831432
- gas_price_wei 6000000

Verified database counts:

- block_logs 5
- chains 1
- blocks 2
- gas_snapshots 2

Completed foundation:

- Chain monitor now writes into market schema
- Legacy block_logs still supported
- blocks table receives live monitor data
- gas_snapshots table receives live monitor data

Next recommended mission:

- Mission 6: Token and pool seed registry

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 6 Completion Record

Date:

- 2026-07-07

Status:

- Complete
- Verified
- Committed

Commit:

- 16e6824 Add token and pool seed registry

Files:

- offchain/config/seed_tokens.json
- offchain/config/seed_pools.json
- offchain/db/seed_registry.py
- offchain/tests/test_seed_registry.py

Verified database counts:

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

Next recommended mission:

- Mission 7: Pool price snapshot simulator

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 7 Completion Record

Date:

- 2026-07-07

Status:

- Complete
- Verified
- Committed

Commit:

- c4bcbfd Add pool price snapshot simulator

Files:

- offchain/db/schema.py
- offchain/simulator/price_snapshot_simulator.py
- offchain/tests/test_price_snapshot_simulator.py

Database table added:

- pool_price_snapshots

Verified database counts:

- pools 2
- pool_price_snapshots 2

Verified snapshots:

- WETH/USDC_DEMO price 3000
- USDC_DEMO/DAI_DEMO price 1

Block used:

- 43831432

Next recommended mission:

- Mission 8: Route builder

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 8 Completion Record

Date:

- 2026-07-07

Status:

- Complete
- Verified
- Committed

Commit:

- e73b359 Add local route builder

Files:

- offchain/db/schema.py
- offchain/simulator/route_builder.py
- offchain/tests/test_route_builder.py

Database table added:

- route_candidates

Verified database counts:

- pool_price_snapshots 2
- route_candidates 2

Verified routes:

- WETH to DAI_DEMO
- DAI_DEMO to WETH

Verified tests:

- 13 Python tests passed

Next recommended mission:

- Mission 9: Opportunity detector

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 9 Completion Record

Date:

- 2026-07-07

Status:

- Complete
- Verified
- Committed

Commit:

- 7b863f5 Add historical data and backtest framework

Files:

- offchain/db/schema.py
- offchain/backtest/__init__.py
- offchain/backtest/historical_data.py
- offchain/backtest/metrics.py
- offchain/backtest/backtest_engine.py
- offchain/tests/test_backtest_framework.py

Tables added:

- historical_candles
- backtest_runs
- backtest_trades

Latest baseline backtest:

- strategy ma_crossover_baseline
- version v1
- symbol WETH_USDC_DEMO
- net return -42.47%
- max drawdown 55.30%
- Sharpe -1.44
- profit factor 0.42
- win rate 29.41%
- trades 17

Investment committee verdict:

- Framework GO
- MA crossover strategy NO-GO

Next recommended mission:

- Mission 10: Strategy metrics and regime analysis

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 10 Completion Record

Date:

- 2026-07-07

Status:

- Complete
- Verified
- Committed

Commit:

- 64644d1 Add strategy regime analysis

Files:

- offchain/db/schema.py
- offchain/backtest/regime_analysis.py
- offchain/tests/test_regime_analysis.py

Tables added:

- market_regime_labels
- strategy_regime_metrics

Verified database counts:

- market_regime_labels 720
- strategy_regime_metrics 5

Regime verdicts:

- bull: NO_GO
- bear: INSUFFICIENT_SAMPLE
- sideways: NO_GO
- high_volatility: INSUFFICIENT_SAMPLE
- low_volatility: NO_GO

Investment committee verdict:

- Regime analysis framework GO
- MA crossover strategy NO-GO
- Live trading NO-GO

Next recommended mission:

- Mission 11: Opportunity detector with backtest validation

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 11 Completion Record

Date:

- 2026-07-08

Status:

- Code complete
- Verified
- Committed

Commit:

- 3502dae Add optimized opportunity detector

Files:

- offchain/db/schema.py
- offchain/detector/__init__.py
- offchain/detector/opportunity_detector.py
- offchain/tests/test_opportunity_detector.py

Table added:

- opportunity_detections

Verified tests:

- 20 tests passed

Verified detector output:

- routes_seen 2
- detections_created 2
- approved 0
- rejected 2

Current rejection reason:

- not_closed_loop_route

Investment committee verdict:

- Detector framework GO
- Current opportunities NO-GO
- Live trading NO-GO

Next recommended mission:

- Mission 12: Closed-loop route builder and backtest validation

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading


---

# Mission 12 Completion Record

Date:

- 2026-07-08

Status:

- Code complete
- Verified
- Committed

Commit:

- bb3ad35 Add closed-loop route builder

Files:

- offchain/config/seed_pools.json
- offchain/simulator/price_snapshot_simulator.py
- offchain/simulator/closed_loop_route_builder.py
- offchain/tests/test_closed_loop_route_builder.py

Main result:

- created closed-loop routes
- approved one simulated profitable closed-loop route
- rejected one weak closed-loop route

Verified database counts:

- pools 3
- pool_price_snapshots 5
- route_candidates 4
- opportunity_detections 6

Approved opportunity:

- closed_loop_arbitrage
- net_edge_bps 150.00000
- risk_score 88

Rejected opportunity:

- closed_loop_arbitrage
- net_edge_bps -246.0784313725490196078431372549019607843
- reasons gross_edge_not_positive and net_edge_below_minimum

Investment committee verdict:

- Closed-loop route framework GO
- Simulated opportunity RESEARCH_GO
- Live trading NO-GO

Next recommended mission:

- Mission 13: Real historical market data ingestion and strategy validation

Still forbidden:

- private key usage
- transaction signing
- mainnet deployment
- real capital
- live trading
