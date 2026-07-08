# ADR-0031.5: AI Learning Dataset + Model Registry

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 31 added paper trading.

The next step is to prepare DeltaGrid for AI-assisted learning from historical scanner, ranking, and paper-trading outcomes.

This mission does not add live trading and does not allow the AI to execute trades.

---

## Decision

Add AI learning dataset and model registry.

Files:

- offchain/backtest/ai_learning_registry.py
- offchain/tests/test_ai_learning_registry.py

Code commit:

- 7889067 Add AI learning dataset registry

---

## Tables Added

- ai_learning_examples
- ai_model_registry

---

## AI Learning Logic

The system collects:

- scanner features
- ranking features
- walk-forward verdict
- liquidation risk verdict
- execution cost verdict
- paper trade outcome when available
- training labels
- model registry status

The system labels examples as:

- profitable / not profitable
- GO / NO-GO training label
- eligible / not eligible for training

---

## Model Registry Logic

The registry records:

- model name
- model version
- model type
- training examples
- eligible examples
- positive labels
- negative labels
- feature names
- metrics
- model parameters
- approval status
- approved_for_research
- approved_for_paper
- approved_for_live

Live approval is always false.

---

## Mission 31.5 Verification

Learning run label:

- mission_31_5_ai_learning_dataset

Model run label:

- mission_31_5_ai_model_registry

Latest run summary:

- example_counts=[(0, 0, 0, 18)] model=('deltagrid_baseline_ai_candidate_scorer', 'mission_31_5_ai_model_registry_v1', 18, 0, 0, 0, 'REJECTED', 0, 0, 0, 'NO_GO_INSUFFICIENT_TRAINING_DATA', 'COLLECT_MORE_PAPER_TRADES')

---

## Investment Committee Verdict

AI learning dataset + model registry:

- GO

Current model status:

- depends on available paper trades and class balance

Live trading:

- NO-GO

Reason:

- AI can only score, classify, and recommend
- AI cannot execute trades
- AI cannot increase risk
- AI cannot bypass investment committee gates
- no private keys
- no real trades

---

## Safety

Still forbidden:

- no autonomous live trading
- no private keys
- no signing
- no real capital
- no mainnet execution
- no risk override
