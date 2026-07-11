# DeltaGrid

Research-first DeFi execution and risk platform.

Core rule:
No real capital until the system passes local tests, fork tests, testnet simulations, paper/demo validation, and manual promotion gates.

Current phase:
Local + testnet research only.

## DeltaGrid Autonomy Architecture

DeltaGrid is being built toward a fully AI-integrated autonomous trading system with self-learning capabilities.

Current status:

- research-first
- shadow and paper-only
- local SQLite evidence trail
- no live trading
- no real capital
- no private keys
- no exchange orders
- no model training yet

Mission 80 intentionally replaces the earlier Human Approval Gate direction with an Autonomous Policy Gate.

The system should not require human approval before every future action. Instead, it should progress through machine-checkable autonomous policy gates.

Current autonomy path:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline training/evaluation/promotion gates
  -> autonomous risk governor
  -> live readiness firewall

Mission 80 approves only autonomous paper-only progression. It does not approve live trading, capital deployment, model training, or exchange execution.

See:

- docs/DELTA_AUTONOMY_ARCHITECTURE.md
- docs/ADR/ADR-0080-autonomous-policy-gate.md

### Mission 81 Autonomous Paper Signal Engine

Mission 81 adds autonomous paper-only signal records after the Mission 80 Autonomous Policy Gate.

These are not live trading signals.

They are:

- paper-only
- observe-only
- no-trade
- no-order
- no-capital
- no-model-training
- no-live-signal

Mission 81 prepares Mission 82 Paper Execution Agent.

Safety remains unchanged:

- live trading disabled
- capital deployment blocked
- no private keys
- no exchange orders
- no real capital
- no model training

## DeltaGrid Autonomous Bot Roadmap

DeltaGrid now has a dedicated full roadmap document:

- docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md

Current verified stage:

- Mission 81 complete
- Autonomous Paper Signal Engine complete
- next mission is Mission 82 Paper Execution Agent

Current honest completion estimate:

- full autonomous AI trading bot: 25 to 30 percent complete
- safe autonomous internal paper-trading system: 40 to 45 percent complete
- live-market paper-trading bot: 25 to 30 percent complete
- real-money autonomous live bot: less than 10 percent complete

Next milestone:

- Mission 82 Paper Execution Agent
- Mission 83 Self-Learning Feedback Loop

Live-market paper trading is planned later, after paper execution, feedback, offline learning, risk governance, and live readiness firewall work.

Real-money live trading is not approved.

### Mission 82 Paper Execution Agent

Mission 82 adds paper execution records after Mission 81 paper-only observe signals.

The agent records paper execution evidence only.

It does not:

- trade live
- deploy capital
- use private keys
- send exchange orders
- train models
- create live trading signals

Next phase:

- Mission 83 Self-Learning Feedback Loop

### Mission 83 Self-Learning Feedback Loop

Mission 83 adds feedback records after Mission 82 paper execution records.

The loop records self-learning evidence only.

It does not:

- train models
- reweight strategies
- trade live
- deploy capital
- use private keys
- send exchange orders
- create live trading signals

Next phase:

- Mission 84 Offline Model Training Harness

### Mission 84 Offline Model Training Harness

Mission 84 adds the offline model training harness after Mission 83 feedback records.

The harness records locked training candidate evidence only.

It does not:

- train models on insufficient data
- create model artifacts
- deploy models
- deploy live systems
- reweight strategies
- trade live
- deploy capital
- use private keys
- send exchange orders
- create live trading signals

Next phase:

- Mission 85 Model Promotion Engine

### Institutional Alpha Research Pivot

Mission 85 is paused until DeltaGrid tests varied strategy families across varied data.

The next active path is:

- Mission 84.5 Institutional Alpha Research Benchmark Lab
- Mission 84.6 Multi-Strategy Backtest Pack
- Mission 84.7 Walk-Forward Robustness Gate
- Mission 84.8 Alpha Candidate Promotion Pack
- Mission 85 Model Promotion Engine

See `docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md`.

### Mission 84.5 Institutional Alpha Research Benchmark Lab

Mission 84.5 creates the alpha research benchmark lab before Mission 85.

It registers:

- strategy families
- crypto, FX, and ETF/macro asset universes
- conservative cost models
- benchmark plan entries
- benchmark safety checks

It does not:

- run backtests yet
- train models
- create model artifacts
- promote models
- reweight strategies
- trade live
- deploy capital
- use private keys
- send exchange orders
- create live trading signals

Next phase:

- Mission 84.6 Multi-Strategy Backtest Pack

<!-- MISSION-84-6:START -->
## Mission 84.6 — Multi-Strategy Backtest Pack

DeltaGrid now includes deterministic local fixture-based paper backtests for all 72 Mission 84.5 benchmark plan entries. Each result includes conservative transaction-cost assumptions and cash, buy-and-hold, and deterministic-random baselines. Results are synthetic research observations only, not profitability claims. Mission 85 remains paused; the next valid phase is Mission 84.7 Walk-Forward Robustness Gate.
<!-- MISSION-84-6:END -->

<!-- MISSION-84-7:START -->
## Mission 84.7 — Walk-Forward Robustness Gate

DeltaGrid now evaluates every Mission 84.6 synthetic-fixture backtest through deterministic expanding-window out-of-sample tests. The gate records per-window performance, baseline comparisons, stability metrics, candidate classifications, governance checks, and reports in SQLite. A robust-fixture classification is not a profitability claim and does not promote a model or strategy. Mission 85 remains paused.
<!-- MISSION-84-7:END -->

<!-- MISSION-84-8:START -->
## Mission 84.8 — Alpha Candidate Promotion Pack

DeltaGrid now performs deterministic review of Mission 84.7 walk-forward results. Eligible results may enter a provisional fixture-only local shadow-research registry. This status does not authorize model training, model promotion, live signals, orders, capital, reweighting, or profitability claims. Mission 85 remains paused.
<!-- MISSION-84-8:END -->
