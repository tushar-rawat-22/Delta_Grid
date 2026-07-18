# ADR-0058: Shadow Research Control Plane and Documentation Registry

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

Missions 53-57 created a shadow operating loop:

- calibrated plans
- shadow ledger entries
- tracking updates
- performance reports
- alert routes

The project now needs a higher-level control plane that runs the loop as one coordinated research cycle and verifies documentation consistency.

## Decision

Add the Shadow Research Control Plane and Documentation Registry.

The control plane orchestrates:

- public dataset reuse
- shadow ledger tracking updater
- shadow tracking performance reporter
- shadow tracking alert invalidation router
- documentation registry check

## Safety

Mission 58 is orchestration-only.

It never:

- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- uses paid APIs
- uses real capital

## Verdict

Live trading remains NO-GO.

Capital deployment remains NO-GO.
