# ADR-0088: Execution and Cost Reality Model

<!-- deltagrid-document-status: HISTORICAL -->

> **Historical architecture decision**
>
> This ADR records a decision accepted for the DeltaGrid phase in which it was
> written. “Accepted” does not grant current research, paper trading, live
> trading, capital, ML, or autonomous authority. See the
> [documentation home](../README.md) and
> [final freeze](../DELTAGRID_FINAL_FREEZE.md) for current status.

Date: 2026-07-12

Status: Accepted after verification

## Context

Mission 87 certified the Mission 86 public real-market dataset for research.

The dataset contains hourly spot, perpetual, mark, and index bars plus settled
funding observations. It does not contain historical order-book depth, queue
position, exchange-account fee tier, true fill latency, or measured market
impact.

A cost model is still required before baseline strategy falsification, but it
must not disguise assumptions as measured microstructure evidence.

## Decision

Mission 88 creates an assumption-bounded execution and cost model.

The model contains:

- Mission 85 fee and slippage floors;
- explicit symbol-level spread assumptions;
- normal, conservative, and severe stress scenarios;
- three hypothetical per-leg notional bands;
- hedge-delay penalties;
- partial-fill penalties;
- rebalance costs;
- funding-reconciliation uncertainty buffers;
- operational uncertainty buffers;
- deterministic hashes and audit checks.

Every non-fee microstructure value is explicitly labeled as an assumption.

Mission 88 makes no order-book precision claim.

## Research Boundary

Mission 88 reads no Mission 86 market bars or funding rows.

Mission 88 performs no strategy backtest, holdout evaluation, return
calculation, parameter selection, model training, model promotion,
profitability analysis, signal generation, order submission, or capital
deployment.

## Mission 89 Authorization

Mission 89 is authorized only for:

`DEVELOPMENT_AND_VALIDATION_BASELINE_FALSIFICATION_ONLY`

The untouched holdout remains sealed for Mission 90.

## Consequences

A passing model status is:

`APPROVED_FOR_BASELINE_FALSIFICATION_WITH_UNCERTAINTY`

The model supplies conservative cost envelopes. It does not claim that those
envelopes are exact realized costs.
