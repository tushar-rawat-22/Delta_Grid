# ADR-0085: Crypto Funding-Carry Research Charter

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

Mission 84 closed with zero real-data validated candidates, zero
training-eligible candidates, and zero model promotions.

The previously planned Mission 85 Model Promotion Engine was never built and
no longer matches the evidence. Promoting or training models before proving a
real-market economic baseline would reverse the correct research order.

## Decision

The legacy Mission 85 Model Promotion Engine plan is:

`RETIRED_UNBUILT_AFTER_MISSION84_CLOSURE`

Mission 85 is redefined as:

`Mission 85 Crypto Funding-Carry Research Charter`

Mission 85 preregisters a falsification-first delta-neutral long-spot,
short-perpetual funding and basis carry hypothesis for BTCUSDT, ETHUSDT, and
SOLUSDT on one venue.

The charter locks:

- the economic hypothesis;
- the three-asset universe;
- the required public market-data streams;
- chronological development, validation, and untouched holdout periods;
- observable trailing-funding entry information;
- a maximum of twelve deterministic parameter variants;
- conservative initial costs;
- rejection criteria;
- holdout and change-control rules;
- all research-only safety restrictions.

## Consequences

Mission 85 does not establish alpha and does not authorize backtesting,
machine learning, model promotion, live trading, exchange orders, private
keys, paid APIs, leverage above one, or capital deployment.

Mission 86 is authorized only to build and certify the required public
real-market datasets.
