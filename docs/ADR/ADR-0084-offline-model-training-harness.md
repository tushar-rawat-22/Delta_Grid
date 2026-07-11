# ADR-0084: Offline Model Training Harness

## Status

Accepted

## Context

Mission 83 created self-learning feedback records.

The next required layer is an offline model training harness. Current feedback evidence is insufficient for actual model training, so Mission 84 records locked training candidates instead of fitting a model.

## Decision

Add Mission 84 Offline Model Training Harness.

It reads:

- ai_self_learning_feedback_runs
- ai_self_learning_feedback_items
- ai_self_learning_feedback_checks

It writes:

- ai_offline_model_training_harness_runs
- ai_offline_model_training_candidates
- ai_offline_model_training_checks
- ai_offline_model_training_reports

## What Mission 84 Approves

Mission 84 may approve:

- offline training harness creation
- locked training candidate records
- handoff to Mission 85 Model Promotion Engine review

## What Mission 84 Does Not Approve

Mission 84 does not approve:

- actual model training on insufficient data
- model artifact creation
- model deployment
- live deployment
- strategy reweighting
- live trading
- real capital
- private key access
- transaction signing
- exchange orders
- paid APIs
- live trading signals
- autonomous live execution

## Consequence

DeltaGrid now has an offline training harness boundary.

The current path is still locked because feedback quality is insufficient.

The next mission is Mission 85 Model Promotion Engine.
