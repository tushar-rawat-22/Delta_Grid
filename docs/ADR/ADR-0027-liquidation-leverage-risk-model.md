# ADR-0027: Liquidation + Leverage Risk Model

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

## Date

2026-07-08

---

## Context

Mission 26 completed funding strategy walk-forward validation.

The next required layer is liquidation and leverage risk modeling.

A funding strategy cannot be promoted until leverage risk, margin buffer, liquidation distance, basis shock, and funding reversal are modeled.

This mission still does not execute trades.

---

## Decision

Add liquidation + leverage risk model.

Files:

- offchain/backtest/liquidation_leverage_risk_model.py
- offchain/tests/test_liquidation_leverage_risk_model.py

Code commit:

- 8558405 Add liquidation leverage risk model

---

## Tables Added

- liquidation_leverage_risk_results
- liquidation_leverage_risk_summary

---

## Risk Logic

The model evaluates:

- short perpetual liquidation price
- liquidation buffer percentage
- adverse spot shock
- adverse basis shock
- stressed mark price
- buffer after stress
- funding reversal loss
- execution cost
- total stress loss
- max safe leverage
- GO / NO-GO verdict

---

## Mission 27 Verification

Run label:

- mission_27_liquidation_leverage_risk_model

Source run:

- mission_23_funding_basis_ingestion

Latest run summary:

- conservative_1_5x_spot20_basis1|1.5|2876.768218640316666666666666666666666667|2094.8181812767|37.32782369146005509641873278236914600553|2.021917808219178082191780821917808219178|3.629764065335753176043557168784029038113|GO_FOR_RESEARCH|PROMOTE_TO_FUNDING_RISK_INTEGRATION || balanced_2x_spot25_basis1_5|2|2588.22576942865|2190.03718951655|18.18181818181818181818181818181818181818|2.932876712328767123287671232876712328767|3.000750187546886721680420105026256564141|GO_FOR_RESEARCH|PROMOTE_TO_FUNDING_RISK_INTEGRATION || aggressive_3x_spot30_basis2|3|2299.683320216983333333333333333333333333|2285.2561977564|0.6313131313131313131313131313131313131167|3.843835616438356164383561643835616438356|2.557544757033248081841432225063938618926|NO_GO_LEVERAGE_TOO_HIGH|REDUCE_TO_MAX_SAFE_LEVERAGE

---

## Investment Committee Verdict

Liquidation + leverage risk model:

- GO

Current scenarios:

- scenario verdicts depend on real market context and risk assumptions

Live trading:

- NO-GO

Reason:

- this is still research-only
- no position sizing engine
- no risk governor
- no exchange failure model
- no real order book execution
- no private keys
- no real trades

---

## Safety

Still forbidden:

- no private keys
- no signing
- no real trades
- no real capital
- no mainnet execution
