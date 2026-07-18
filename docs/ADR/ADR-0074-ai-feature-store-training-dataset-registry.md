# ADR-0074: AI Feature Store and Training Dataset Registry

<!-- deltagrid-document-status: HISTORICAL -->

> **Historical architecture decision**
>
> This ADR records a decision accepted for the DeltaGrid phase in which it was
> written. “Accepted” does not grant current research, paper trading, live
> trading, capital, ML, or autonomous authority. See the
> [documentation home](../README.md) and
> [final freeze](../DELTAGRID_FINAL_FREEZE.md) for current status.

## Status

Accepted

## Context

Mission 73 created paper-only AI outcome dataset rows and a feature-store handoff.

The rows are pending paper outcomes and are not training-eligible. DeltaGrid needs a registry layer that records feature-store entries and training dataset registry entries without enabling training or trading.

## Decision

Add the AI Feature Store and Training Dataset Registry.

Files:

- offchain/ai_dataset/feature_store_training_registry.py
- offchain/tests/test_feature_store_training_registry.py

Code commit:

- 9a40c11 Add AI feature store training dataset registry

The registry reads:

- ai_outcome_dataset_builds
- ai_outcome_dataset_rows
- ai_outcome_dataset_quality_checks
- ai_outcome_dataset_handoffs

The registry writes:

- ai_feature_store_training_registries
- ai_feature_store_feature_records
- ai_training_dataset_registry_entries
- ai_feature_store_training_registry_checks
- ai_feature_store_training_registry_reports

## Safety

Mission 74 does not train a model.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital
- performs autonomous strategy reweighting
- runs autonomous execution

Training remains locked until paper outcomes are collected.

## Consequence

DeltaGrid now has a feature-store and training dataset registry layer, but training remains disabled.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO

Autonomous trading remains:

- NO-GO
