# DeltaGrid Architecture State

## Shadow Research Control Plane

Mission 58 adds the Shadow Research Control Plane.

It orchestrates:

1. public data orchestration
2. shadow ledger tracking updater
3. shadow tracking performance reporter
4. shadow tracking alert and invalidation router
5. documentation registry

## Safety Boundary

The control plane is not an execution engine.

It cannot:

- place orders
- sign transactions
- use private keys
- deploy capital
- enable live trading

## Multi-Strategy Research Factory Layer

Mission 59 adds a strategy research factory layer.

Inputs:

- historical public funding rates
- historical public basis observations

Outputs:

- strategy registry
- strategy candidates
- promotion shortlist
- watchlist
- rejection reasons
- factory report

Safety boundary:

- this layer produces research candidates only
- it does not place trades
- it does not allocate capital

---

## Data Quality and Regime Intelligence Layer

Mission 60 adds the data quality and regime intelligence layer.

Inputs:

- historical public funding rates
- historical public basis observations
- multi-strategy research candidates

Outputs:

- symbol data-quality reports
- market risk state
- candidate regime gates
- regime intelligence report

This layer sits between strategy research and promotion review.

---

## Shadow Portfolio Simulation Layer

Mission 61 adds the portfolio simulation layer.

Inputs:

- Mission 60 candidate regime gates

Outputs:

- portfolio simulation report
- allocation records
- portfolio risk report

This layer sits between regime-gated strategy research and promotion board review.

## Research Promotion Board Layer

Mission 62 adds a governance layer above the shadow portfolio simulator.

Inputs:

- shadow portfolio simulations
- shadow portfolio allocations
- shadow portfolio risk reports

Outputs:

- board review record
- board evidence items
- board decision record

This layer decides whether the portfolio can advance to paper sandbox research only.
