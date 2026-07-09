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
