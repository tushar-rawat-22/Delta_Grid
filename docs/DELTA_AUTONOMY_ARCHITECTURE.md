# DeltaGrid Autonomy Architecture

DeltaGrid is being built as a research-first autonomous AI trading system.

The long-term goal is:

AI observes markets
AI generates research hypotheses
AI tests them in paper and shadow mode
AI records outcomes
AI learns from those outcomes
AI promotes better versions through policy gates
AI eventually operates autonomously inside strict risk limits

## Current Safety State

DeltaGrid is not a live trading bot yet.

Current hard boundaries:

- live trading is disabled
- capital deployment is blocked
- no private keys are used
- no transaction signing is performed
- no exchange orders are sent
- no paid APIs are required
- model training is still locked
- live signal generation is blocked
- autonomous live execution is blocked
- automatic live strategy reweighting is blocked

## Why Autonomous Policy Gates Exist

A permanent human approval gate before every action would weaken the objective of building an autonomous AI trading system.

Instead, DeltaGrid uses autonomous policy gates.

A policy gate is a machine-checkable rule layer that determines whether the system may move to the next safe phase.

Example policy question:

Can the system move from research recommendations to autonomous paper signals?

Only if:

- the source recommendation run exists
- source checks passed
- no safety breach exists
- no leakage breach exists
- no live signal is generated
- no execution is allowed
- no capital deployment is allowed
- model training remains disabled
- the next phase is paper-only

## Mission 80 Architecture Correction

Mission 80 intentionally replaces the earlier Human Approval Gate direction.

Old direction:

Mission 80: Human Approval Gate

New direction:

Mission 80: Autonomous Policy Gate

This aligns better with the target system:

- fully AI-integrated
- autonomous
- self-learning
- policy-controlled
- risk-gated

## Current Mission Path

Completed path through Mission 79:

- Mission 76: AI Label Quality and Leakage Guard
- Mission 77: AI Offline Evaluation Harness
- Mission 78: AI Offline Evaluation Governance Board
- Mission 79: AI Research Recommendation Engine

Corrected path from Mission 80 onward:

- Mission 80: Autonomous Policy Gate
- Mission 81: Autonomous Paper Signal Engine
- Mission 82: Paper Execution Agent
- Mission 83: Self-Learning Feedback Loop
- Mission 84: Offline Model Training Harness
- Mission 85: Model Promotion Engine
- Mission 86: Autonomous Risk Governor
- Mission 87: Live Readiness Firewall

## Important Distinction

Autonomous does not mean reckless.

DeltaGrid autonomy means the system can progress automatically only when objective safety policies pass.

It does not mean the system can trade real money without controls.

## Current Approved Next Step

Mission 80 may approve only Mission 81 Autonomous Paper Signal Engine.

That is paper-only.

It is not live trading.
It is not capital deployment.
It is not model training.
It is not exchange execution.

## Self-Learning Direction

The self-learning loop will be introduced safely:

paper signal
  -> paper outcome
  -> labeled dataset
  -> quality guard
  -> offline evaluation
  -> model training harness
  -> model promotion policy
  -> paper deployment

Live deployment will require a later, separate live-readiness firewall.
