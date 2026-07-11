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
