# ADR-0037: Shadow Research Decision Gate

## Status

Accepted

## Context

Mission 36 added shadow replay performance reporting.

DeltaGrid can now summarize replay metrics, but it needs a strict board-level decision gate before any future automation is allowed.

The gate must preserve the project's non-negotiable safety constraints.

## Decision

Add a shadow research decision gate.

Files:

- offchain/backtest/shadow_research_decision_gate.py
- offchain/tests/test_shadow_research_decision_gate.py

Code commit:

- 9616a4f Add shadow research decision gate

The gate reads Mission 36 SQLite table:

- shadow_replay_performance_reports

The gate writes:

- shadow_research_decision_gate_reports

It evaluates:

- replay count
- scenario count
- pipeline run count
- candidate count
- approved candidates
- rejected candidates
- shadow paper positions
- approval rate
- rejection rate
- paper position rate
- live trading breach count

It produces:

- board-style gate decision
- live trading decision
- capital deployment decision
- approved next stage
- CEO vote
- CTO vote
- CFO/Quant Lead vote
- markdown report

## Safety

The decision gate is governance-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All current decisions must keep:

- live trading BLOCKED
- capital deployment BLOCKED

## Mission 37 Verification

Expected verification:

- Mission 37 unit tests pass
- full offchain suite passes
- decision gate approves only shadow-paper observation
- live trading decision remains BLOCKED
- capital deployment decision remains BLOCKED
- decision report persists in SQLite

## Verdict

Mission 37 improves governance.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Next valid phase:

- Continue shadow research infrastructure.
