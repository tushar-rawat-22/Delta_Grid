# ADR-0087: Dataset Certification and Quality Gate

Date: 2026-07-12

Status: Accepted after verification

## Context

Mission 86 captured the public real-market data required by the locked Mission
85 funding-carry charter.

Mission 86 established ingestion completeness and provenance preservation, but
its datasets remained:

`UNCERTIFIED_PENDING_MISSION87`

A complete timestamp count alone does not prove research quality. The data must
be independently checked against its raw evidence and against structural
market-data invariants before it can enter an execution-cost model or strategy
backtest.

## Decision

Mission 87 creates an append-only certification layer over Mission 86.

Mission 87 verifies:

- Mission 85 contract and Mission 86 manifest lineage;
- raw gzip file containment and integrity;
- raw body and request-response hashes;
- raw JSON row counts;
- exact raw-to-normalized equivalence;
- hourly continuity;
- chronological development, validation, and holdout coverage;
- duplicate and out-of-window observations;
- OHLC and volume integrity;
- funding settlement alignment and continuity;
- funding-rate and funding mark-price validity;
- spot, perpetual, mark, and index cross-stream consistency;
- absence of synthetic or fallback data;
- research-only safety locks.

Mission 87 does not mutate the Mission 86 source rows.

## Holdout Boundary

The untouched holdout is inspected only through blinded structural checks.

Mission 87 does not report holdout price values, returns, strategy outcomes, or
performance statistics. It does not select parameters or consume the
single-use strategy-evaluation holdout budget.

## Consequences

A successful certificate has status:

`CERTIFIED_FOR_RESEARCH_PENDING_EXECUTION_COST_MODEL`

It authorizes Mission 88 to construct an execution and cost reality model.

It does not authorize:

- strategy backtesting;
- model training or promotion;
- live signals or orders;
- private keys or signing;
- leverage;
- capital deployment;
- profitability claims.
