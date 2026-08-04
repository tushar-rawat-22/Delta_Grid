# DeltaGrid

DeltaGrid is Tushar Rawat's private quantitative research and investment-system
project. I built it to test cryptocurrency trading ideas under realistic data,
cost, chronology, and risk constraints—and to preserve negative results instead
of turning attractive backtests into premature trading claims.

## Current status

**There is no validated profitable strategy. No candidate is selected.**

Paper trading and live trading are not authorized. Exchange access, credential
access, and capital deployment are not authorized. Software tests do not
establish alpha.

The final project freeze was published at commit
`ce82c5b887a08185b7acceb35480783d02eb0b5d`. It closed the authorized research
families without a promotable candidate. Later work added narrow research and
observation infrastructure, but it did not reopen strategy research or grant
trading authority.

## Why I built it

I wanted the process to start with a falsifiable hypothesis rather than an
indicator: freeze the rules, verify when data became available, model costs,
test chronologically, and reject the idea when the evidence is weak. DeltaGrid
separates research, validation, risk, execution, operations, and review so that
one component cannot promote its own result.

## Research outcome

| Research family | Recorded outcome |
|---|---|
| Synthetic benchmark work | Built research infrastructure; did not validate real-market alpha |
| Funding and basis carry | Rejected |
| Directional strategies | Rejected |
| Macro-regime hypothesis | Rejected before strategy construction |
| Trade-flow and lead-lag hypotheses | Rejected in development |

Alpha Search B was rejected on development data. Its publication records zero
scoped validation access and zero scoped holdout access. The detailed results,
statistical controls, and evidence links are in the
[Final Project Report](docs/DELTAGRID_FINAL_PROJECT_REPORT.md).

The Alpha Search B rejection was published at
`a31f4da4fc8b52ca2fa6aaad697350d6e9180736`. That commit is the historical
research base, **not a permanent assertion about every future repository
HEAD**. No Alpha Search B candidate was authorized for Freqtrade translation.

## What exists now

Historical infrastructure includes public-data acquisition, dataset
certification, causal features, event-driven simulation, execution-cost and
risk models, sealed evaluation boundaries, statistical controls, and Freqtrade
parity work. Its existence is not current permission to collect protected data,
run a candidate, access an exchange, or trade.

The current backend sequence is deliberately narrower:

| Mission | Result |
|---|---|
| 93 | Audited and froze the interfaces needed before cockpit work |
| 94 | Added budgeted admission and immutable trial reservation for permitted synthetic controls |
| 95 | Added deterministic execution and independently verifiable result bundles |
| 96A | Added read-only ledger and verified-result projections |
| 96B | Added a loopback-only, read-only cockpit |
| 97 | Added one durable observation workflow with leases, fencing, bounded retries, recovery, and immutable manifests |

Mission 97 was published at commit
`8afa19a06dd6f1b100befce067107c1fa347d471`. Its publication reported 1,153
passing tests and one third-party `websockets.legacy` deprecation warning. Those
tests cover software behavior and repository invariants; they do not establish
alpha.

## Provisional roadmap: Missions 98–107

This is planning direction, not authorization. Each mission would require its
own reviewed contract before it could use new data, execute research, access an
exchange, paper trade, live trade, or deploy capital.

| Mission | Planning direction |
|---|---|
| 98 | Choose the next permitted research action from fixed evidence, budgets, and policy |
| 99 | Maintain reproducible, certified, availability-aware market datasets |
| 100 | Provide a general event-driven research runtime for registered strategies and controls |
| 101 | Enforce independent development, validation, holdout, replication, and multiple-testing gates |
| 102 | Observe approved candidates on current data without exchange orders |
| 103 | Add durable paper execution, accounting, and reconciliation |
| 104 | Govern portfolio allocation, exposure, drawdown, leverage, and kill switches independently |
| 105 | Isolate exchange connectivity and restricted credentials behind risk checks |
| 106 | Consider a manually activated, severely limited tiny-capital pilot only after independent approval |
| 107 | Connect research, validation, observation, deployment, reduction, and retirement under separate controls |

## Running the tests

The repository does not currently document a verified fresh-clone bootstrap for
the complete test environment. For an already configured checkout with the
ignored local virtual environment at `offchain/.venv`, run:

```bash
env -u PYTHONPATH \
PYTHONDONTWRITEBYTECODE=1 \
offchain/.venv/bin/python -m pytest \
  -p no:cacheprovider \
  offchain/tests \
  -q
```

The virtual environment is local and ignored; it is not included in a fresh
clone.

## Documentation

- [Documentation home](docs/README.md)
- [Final freeze](docs/DELTAGRID_FINAL_FREEZE.md)
- [Current research policy](docs/RESEARCH_POLICY.md)
- [Current risk policy](docs/RISK_POLICY.md)
- [Current safety invariants](docs/SAFETY_INVARIANTS.md)
- [Evidence summaries](docs/research-summaries/README.md)
- [Operator guide](docs/OPERATOR_GUIDE.md)
- [Documentation registry](docs/documentation-status.json)

<details>
<summary>Historical compatibility notes</summary>

These markers are retained for historical documentation verification. They
describe earlier repository phases and do not override the current project
status above.

Committed pre-freeze evidence records 37 passing Alpha Search B/reset focused
tests and 715 passing complete off-chain tests, with one third-party
`websockets.legacy` deprecation warning. These are historical pre-freeze
baselines, not the full-suite total at the published final freeze.

<!-- MISSION-84-CLOSURE:START -->
### Mission 84 Closure

Mission 84 closed its deterministic synthetic-fixture pipeline with zero
real-data validated alpha candidates. The historical fixture-screening records
remain preserved but authorize no model training, strategy promotion, live
signal, order, capital, or profitability claim. There is no Mission 84.9.
<!-- MISSION-84-CLOSURE:END -->

<!-- MISSION-85-CHARTER:START -->
### Mission 85 Crypto Funding-Carry Research Charter

Mission 85 locked a falsification-first funding-carry charter before real-market
collection. It did not prove profitability and prohibited ML rescue, live
trading, orders, and capital. Its next authorized data-only phase was Mission 86
Real-Market Data Foundation.
<!-- MISSION-85-CHARTER:END -->

<!-- MISSION-86-DATA-FOUNDATION:START -->
### Mission 86 Real-Market Data Foundation

Mission 86 implemented public-data acquisition, normalization, provenance, and
deterministic manifests. It performed no strategy backtest or profitability
analysis. Its output remained `UNCERTIFIED_PENDING_MISSION87` until Mission 87
Dataset Certification and Quality Gate.
<!-- MISSION-86-DATA-FOUNDATION:END -->

<!-- MISSION-87-CERTIFICATION:START -->
### Mission 87 Dataset Certification and Quality Gate

Mission 87 certified structural data quality and lineage. It performed no
strategy backtest or holdout performance evaluation. The next historical phase
was Mission 88 Execution and Cost Reality Model.
<!-- MISSION-87-CERTIFICATION:END -->

<!-- MISSION-88-COST-MODEL:START -->
### Mission 88 Execution and Cost Reality Model

Mission 88 completed an assumption-bounded cost model with no strategy backtest
and no order-book precision claim. Its next historical phase was
Mission 89 Baseline Strategy Falsification.
<!-- MISSION-88-COST-MODEL:END -->

</details>
