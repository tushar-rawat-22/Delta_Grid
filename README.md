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
