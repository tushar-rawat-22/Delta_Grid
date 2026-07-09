# DeltaGrid Safety Invariants

## Non-Negotiable Safety Invariants

These remain true until a future approved capital readiness review changes them:

- live_trading = DISABLED
- capital_deployment = BLOCKED
- live_order_sent = 0
- no private keys
- no signing
- no exchange orders
- no paid APIs
- no real capital

## Mission 58 Boundary

The Shadow Research Control Plane may orchestrate research stages only.
It may not execute trades.
