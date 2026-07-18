# ADR-0051: Funding and Basis Alpha Scanner

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

Mission 50 created the first historical public funding and basis dataset using real Binance public data.

DeltaGrid now needs a scanner that ranks symbols by funding strength, funding consistency, basis, spread, and cost-adjusted carry.

## Decision

Add a funding and basis alpha scanner.

Files:

- offchain/backtest/funding_basis_alpha_scanner.py
- offchain/tests/test_funding_basis_alpha_scanner.py

Code commit:

- 4c49417 Add funding and basis alpha scanner

The scanner reads:

- historical_public_funding_rates
- historical_public_basis_observations
- historical_public_funding_basis_dataset_reports

The scanner writes:

- funding_basis_alpha_candidates
- funding_basis_alpha_scanner_reports

The scanner computes:

- average funding rate bps
- latest funding rate bps
- positive funding ratio
- negative funding ratio
- funding volatility
- latest basis bps
- latest spread bps
- estimated entry/exit cost
- cost-adjusted carry bps
- alpha score
- candidate rank
- scanner status

## Safety

Mission 51 is shadow-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

All scanner records preserve:

- live_trading = DISABLED
- live_order_sent = 0
- capital_deployment = BLOCKED

## Verdict

Mission 51 turns public datasets into ranked alpha candidates.

Live trading remains:

- NO-GO

Capital deployment remains:

- NO-GO
