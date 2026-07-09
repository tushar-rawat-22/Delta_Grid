# ADR-0080: Autonomous Policy Gate

## Status

Accepted

## Context

Mission 79 produced research-only recommendations and originally pointed toward a Human Approval Gate.

The project objective is a fully AI-integrated autonomous trading bot with self-learning capabilities. A permanent human approval gate before every action would conflict with that objective.

DeltaGrid therefore changes direction:

- not permanent human approval before every step
- yes to machine-checkable autonomous policy gates
- yes to autonomous progression in paper and shadow mode first
- no to live trading until separate live-readiness firewalls exist

## Decision

Replace the old Mission 80 Human Approval Gate direction with Mission 80 Autonomous Policy Gate.

The Autonomous Policy Gate checks objective rules before allowing the next autonomous paper-only step.

It reads:

- ai_research_recommendation_runs
- ai_research_recommendation_items
- ai_research_recommendation_checks

It writes:

- ai_autonomous_policy_gate_runs
- ai_autonomous_policy_gate_rules
- ai_autonomous_policy_gate_decisions
- ai_autonomous_policy_gate_checks
- ai_autonomous_policy_gate_reports

## Policy Rules

Mission 80 evaluates machine-checkable rules:

- source recommendation run exists
- source recommendation engine is ready
- source failed checks are zero
- safety breach count is zero
- leakage breach count is zero
- model training remains disabled
- no live signals are produced
- no execution is permitted
- no capital deployment is permitted
- live trading remains disabled
- only autonomous paper progression may be approved
- baseline accuracy is not treated as profitability evidence

## What Mission 80 Approves

Mission 80 may approve autonomous paper-only progression.

Specifically, it may approve handoff to Mission 81 Autonomous Paper Signal Engine.

## What Mission 80 Does Not Approve

Mission 80 does not approve:

- live trading
- real capital
- private key access
- transaction signing
- exchange orders
- paid APIs
- model training
- live trading signals
- autonomous live execution
- automatic live strategy reweighting

## Consequence

DeltaGrid now moves toward autonomy through machine-checkable policy gates instead of permanent manual approval.

The long-term architecture becomes:

research recommendations
  -> autonomous policy gate
  -> autonomous paper signal engine
  -> paper execution agent
  -> self-learning feedback loop
  -> offline training/evaluation/promotion gates
  -> autonomous risk governor
  -> live readiness firewall

Live trading remains NO-GO.
Capital deployment remains NO-GO.
Model training remains NO-GO.
Live signals remain NO-GO.
