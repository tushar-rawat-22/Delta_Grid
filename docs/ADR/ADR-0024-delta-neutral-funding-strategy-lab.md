# ADR-0024: Delta-Neutral Funding Strategy Lab

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 22 added the funding / basis data model.

Mission 23 added public Binance funding / basis ingestion.

Mission 24 evaluates whether the ingested data produces a research-worthy delta-neutral funding candidate.

This mission still does not execute trades.

---

## Decision

Add delta-neutral funding strategy lab.

Files:

- offchain/backtest/delta_neutral_funding_lab.py
- offchain/tests/test_delta_neutral_funding_lab.py

Code commit:

- 2be3c61 Add delta neutral funding strategy lab

---

## Tables Added

- delta_neutral_funding_lab_results
- delta_neutral_funding_lab_summary

---

## Strategy Evaluation

The lab evaluates:

- funding observation count
- average annualized funding rate
- latest annualized funding rate
- minimum annualized funding rate
- positive funding ratio
- spot/perp basis
- basis penalty
- execution cost assumption
- expected edge
- stress edge
- estimated 30-day carry
- final GO / NO-GO verdict

---

## Mission 24 Verification

Run label:

- mission_24_delta_neutral_funding_lab

Source run:

- mission_23_funding_basis_ingestion

Latest run summary:

- 20|6.46707000|3.26748000|1.66330500|100|-0.03464239274341806018053250034036187713858|6.258409401814145484954866874914909530715|1.454644401814145484954866874914909530715|0.5143898138477379850647835787601295504696|NO_GO_LOW_AVG_FUNDING|WAIT_FOR_HIGHER_AVERAGE_FUNDING

---

## Investment Committee Verdict

Delta-neutral funding lab:

- GO

Current ETHUSDT candidate:

- verdict depends on latest real funding conditions

Live trading:

- NO-GO

Reason:

- this is still research-only
- no liquidation model
- no exchange failure model
- no execution simulator
- no funding-rate path backtest
- no position sizing engine
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
