# DeltaGrid

DeltaGrid is Tushar Rawat's single-user quantitative research and investment-system
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

Mission 99 now adds a temporal market-data control plane. It can create and
independently certify immutable synthetic releases, audit Mission 86/87
metadata, classify recovery evidence, and resolve synthetic records as of a
decision time. It makes no network requests, and real-data research resolution
remains unauthorized.

Mission 100 adds one deliberately narrow network authority: bounded,
unauthenticated collection from frozen Binance public market-data endpoints.
It records forward receipt time, raw evidence, retries, revisions, checkpoints,
and local backup evidence in a private runtime. It still does not authorize
strategy research, real-data research resolution, exchange accounts, credentials,
orders, paper/live trading, or capital.

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
| 98 | Added a deterministic, decision-only Research Director that verifies Mission 97 evidence and emits one non-executable recommendation |
| 99 | Added immutable, revision-aware market-data custody, independent certification, deterministic recovery inspection, and a bounded synthetic as-of resolver |
| 100 | Added bounded forward public-market acquisition with immutable raw evidence, append-only receipts, clock checks, revisions, checkpoints, and local backup verification |

Mission 97 was published at commit
`8afa19a06dd6f1b100befce067107c1fa347d471`. Its publication reported 1,153
passing tests and one third-party `websockets.legacy` deprecation warning. Those
tests cover software behavior and repository invariants; they do not establish
alpha.

## Provisional roadmap: Missions 101–109

This is planning direction, not authorization. Each mission requires its own
reviewed contract before it can use new authority. Mission 100 collects forward
provider evidence, but that evidence is not yet admitted to result-bearing
research.

| Mission | Planning direction |
|---|---|
| 101 | Add a founder-approved research reopening authority and narrow experiment permits, including the reviewed bridge from Mission 100 evidence into Mission 99 custody |
| 102 | Provide a general event-driven research runtime that can execute only permitted experiments |
| 103 | Enforce independent development, validation, holdout, replication, and multiple-testing gates |
| 104 | Observe approved candidates on current data without exchange orders |
| 105 | Add durable paper execution, accounting, and reconciliation |
| 106 | Govern portfolio allocation, exposure, drawdown, leverage, and kill switches independently |
| 107 | Isolate exchange connectivity and restricted credentials behind independent risk checks |
| 108 | Consider a manually activated, severely limited tiny-capital pilot only after independent approval |
| 109 | Connect research, validation, observation, deployment, reduction, and retirement under separate bounded controls |

## Public review and rights

This repository is visible for portfolio demonstration, inspection, and
professional review. It is not open source, and public visibility does not
grant general permission to use, copy, modify, redistribute, deploy, host, or
commercialize it. See the [LICENSE](LICENSE) for the concise terms and contact
address.

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
- [Autonomous Research Director](docs/DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR.md)
- [Autonomy constitution v1](docs/DELTAGRID_AUTONOMY_CONSTITUTION.md)
- [Autonomy constitution v2](docs/DELTAGRID_AUTONOMY_CONSTITUTION_V2.md)
- [Temporal Market Data Control Plane](docs/DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE.md)
- [Forward Market Data Acquisition](docs/DELTAGRID_FORWARD_MARKET_DATA_ACQUISITION.md)
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
