# ADR-0033: Unified Free Shadow Research Runner

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

DeltaGrid has reached the research dashboard and alerting stage. The system already contains scanner, ranking, paper-trading, AI learning registry, and dashboard alert components.

The next risk is fragmentation: running these components separately can create inconsistent run labels, incomplete reporting, and unclear promotion decisions.

The user also has a hard constraint:

- zero capital available for trading
- no paid APIs
- no cloud bill
- no live execution
- no private key usage
- no exchange signing

Therefore, the next mission must unify the research loop while preserving the project source-of-truth: research first, no real capital, and no live trading until formal promotion gates are passed.

## Decision

Add a unified Mission 33 runner:

```text
offchain/backtest/research_pipeline_runner.py
```

The runner operates only in:

```text
SHADOW_MODE
```

It runs the logical research sequence:

```text
funding scanner
→ candidate ranking
→ execution cost/slippage simulation
→ liquidation/leverage risk model
→ paper trading engine
→ AI learning registry
→ research dashboard alerts
→ final markdown report
```

The Mission 33 runner persists results into SQLite tables:

```text
research_pipeline_runs
research_pipeline_stage_results
research_pipeline_reports
```

The runner is deliberately safe by default. If no explicit candidates are supplied, it generates conservative local shadow candidates that are expected to be rejected. This ensures the default behavior fails closed.

## Safety Rules

Mission 33 must never:

- read private keys
- sign transactions
- send exchange orders
- require paid APIs
- require cloud infrastructure
- require live capital
- enable live trading

Live trading remains:

```text
DISABLED
```

The default verdict remains:

```text
RESEARCH_PIPELINE_NO_GO_WAIT_FOR_EDGE_NO_LIVE_TRADING
```

A candidate may open a shadow paper position only when strict filters pass, but even then the system verdict remains shadow-only and no live orders are sent.

## Consequences

Positive:

- one command can produce a full research verdict
- every run gets a single run label
- stage results are stored consistently
- rejected candidates preserve rejection reasons
- reports are reproducible
- the system remains free and safe

Negative:

- the runner is not a live trading engine
- the first version is intentionally conservative
- the baseline runner does not claim profitability
- live execution remains out of scope

## Mission 33 Success Criteria

Mission 33 is complete when:

- the runner module exists
- tests pass
- SQLite persistence works
- default behavior fails closed
- approved candidates can create shadow paper positions
- live trading remains disabled in every test
- documentation is committed

## Promotion Rule

Passing Mission 33 does not approve live trading.

The next valid phase is continued shadow research, not real-money execution.
