# DeltaGrid

**There is no validated profitable strategy. No candidate is selected.**

RAB-1 is prospectively locked, but no result has been opened.

Paper trading and live trading are not authorized. Exchange access, credential access, and capital deployment are not authorized. Software tests do not establish alpha.

DeltaGrid is a single-user quantitative research system built to answer a harder question than “does this backtest look good?”: **can a trading hypothesis survive causal data handling, realistic costs, preregistered rules, independent verification, and deliberately closed promotion gates?**

I built the project around falsification. A failed hypothesis stays in the record. A passing software test is not treated as evidence of alpha. A component being implemented does not give it permission to trade.

## Current status

| Boundary | Current state |
|---|---|
| Result-bearing strategy research | One exact RAB-1 prospective programme is locked; no result has been opened |
| Mission 104 candidate observation | Not authorized; there is no qualified candidate to observe |
| Paper trading | Not authorized |
| Live trading | Not authorized |
| Exchange / credential access | Not authorized |
| Orders / portfolio allocation / capital deployment | Not authorized |
| P1.1 public projection | Implemented; authority effect `NONE` |
| Founder research engine | Implemented under `web/`; delayed public data only, `NON_RAB1_RESEARCH_ONLY` |

The final research freeze was published at commit `ce82c5b887a08185b7acceb35480783d02eb0b5d`. Later missions added narrower custody, admission, execution, statistical-governance, and public-projection infrastructure without rewriting the negative research result or granting trading authority.

## What the project actually contains

DeltaGrid is not one strategy script. The repository is a set of explicit boundaries that can be checked independently:

- **Causal data custody** — records availability and revision timing instead of assuming every value was knowable at event time.
- **Deterministic research execution** — exact admitted trials are bound to immutable specifications and replayable accounting.
- **Cost-aware simulation** — fees, execution assumptions, chronology, and cash flows are part of the test rather than added after a result looks attractive.
- **Sealed progression** — development, replication, validation, and holdout stages are kept separate and require their own authority.
- **Finite statistical programmes** — multiplicity and candidate selection are fixed at programme level rather than reset until something passes.
- **Independent verification** — important result and projection packages can be checked without trusting the component that produced them.
- **Negative-evidence preservation** — rejected families and failed activation attempts remain part of the project history.
- **Authority separation** — software capability, research permission, observation, paper execution, live execution, credentials, and capital are separate states.

This repository is now the single active DeltaGrid codebase. The public core, observer, founder Worker, and research-engine source are reviewed together. Secrets, founder-authored research records, protected evidence, and private operating history remain outside Git; publishing the control code does not publish credentials or grant authority.

## Why I built it

Most trading prototypes make it easy to search, tune, and promote. DeltaGrid deliberately makes those actions harder.

The process starts with a falsifiable hypothesis and an exact evidence boundary: freeze the rules, establish when inputs became available, model costs, test chronologically, and reject the idea when the evidence is weak. Research, validation, risk, execution, operations, and review are separated so that one component cannot silently promote its own result.

That makes the project useful even when the research answer is “no.” The engineering record shows what was tested, what failed, what remains closed, and what would have to be proven before a higher-authority stage could exist.

## Research record

| Research family | Recorded outcome |
|---|---|
| Synthetic benchmark work | Built research infrastructure; did not validate real-market alpha |
| Funding and basis carry | Rejected |
| Directional strategies | Rejected |
| Macro-regime hypothesis | Rejected before strategy construction |
| Trade-flow and lead-lag hypotheses | Rejected in development |

Alpha Search B was rejected on development data. Its publication records zero scoped validation access and zero scoped holdout access. The detailed results, statistical controls, and evidence links are in the [Final Project Report](docs/DELTAGRID_FINAL_PROJECT_REPORT.md).

The Alpha Search B rejection was published at `a31f4da4fc8b52ca2fa6aaad697350d6e9180736`. That commit is the historical research base, **not a permanent assertion about every future repository HEAD**. No Alpha Search B candidate was authorized for Freqtrade translation.

## Engineering sequence

Historical infrastructure includes public-data acquisition, dataset certification, causal features, event-driven simulation, execution-cost and risk models, sealed evaluation boundaries, statistical controls, and Freqtrade parity work. Its existence is not current permission to collect protected data, run a candidate, access an exchange, or trade.

Mission 99 established the revision-aware temporal market-data control plane that the later forward-custody work builds on.

The current backend and projection sequence is deliberately narrower:

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
| 101 | Added independently certified forward custody, exact development dataset descriptors, finite founder permits, and metadata-only Admission V2; result-bearing execution remains closed |
| 102 | Added consumed-permit-bound development execution, immutable trial specifications, causal selected-value loading, deterministic accounting, independent replay, and Mission 94 finalization; the prospective RAB-1 contract now authorizes exactly one four-variant family |
| 103 | Added campaign-level anti-reset governance, exact program-wide statistics, one-candidate freeze, prospective protected partitions, and one-use founder-authorized protected progression; RAB-1 authorizes exactly one sealed adapter and one sealed evaluator |
| P1.1 | Added a deterministic repository-only public projection package and independent verifier; private runtimes, market values, protected data, and trading authority remain closed |

Mission 97 was published at commit `8afa19a06dd6f1b100befce067107c1fa347d471`. Its publication reported 1,153 passing tests and one third-party `websockets.legacy` deprecation warning. Those tests cover software behavior and repository invariants; they do not establish alpha.

### A few important boundaries in the later missions

Mission 100 introduced one deliberately narrow network authority: bounded, unauthenticated collection from frozen Binance public market-data endpoints. Its controlled production activation completed on 2026-08-08 after a first live attempt failed closed and was preserved for review. The mission records receipt time, raw evidence, retries, revisions, checkpoints, and local backup evidence, but does not make that evidence research-admissible.

Mission 101 governs the bridge from an independently verified Mission 100 backup into a distinct forward-custody profile. It can certify the evidence, describe an immutable real-market development dataset, record a finite founder-controlled permit, and reserve metadata-only admission. It does not execute an experiment or open validation/holdout values.

Mission 102 provides a deterministic event-driven runtime for an exact already-admitted `REAL_MARKET_DEVELOPMENT` trial. The prospective RAB-1 contract registers exactly one four-variant family; no RAB-1 result has yet been opened.

Mission 103 adds programme-level statistical governance, exact empirical p-values with program-wide Holm correction, at most one fixed candidate, and prospective one-use `REPLICATION`, `VALIDATION`, and `HOLDOUT` openings. RAB-1 registers one exact 24-hour sign-flip adapter and one authoritative-M102-metrics evaluator. Its maximum verdict, `QUALIFIED_FOR_M104_OBSERVATION`, has authority effect `NONE`.

P1.1 adds a public projection boundary over repository/public-contract state. It is deterministic and independently verifiable, but it does not expose private runtime state or create a path back into DeltaGrid authority.

## Mission 103 status and provisional roadmap: Missions 104–109

This remains planning direction, not authorization. The [Mission-104 readiness lock](docs/M104_READINESS_LOCK.md) is the only active prospective programme. It requires 180 days of forward-observed evidence and three protected-stage founder approvals. Before a passing holdout, Mission 104 remains not authorized. A failure closes RAB-1 without a replacement or rescue.

| Mission | Planning direction |
|---|---|
| 101 | Implemented the founder-controlled governance, forward-custody, exact-dataset, permit, and metadata-only development-admission machinery; no result-bearing execution |
| 102 | Implemented a general event-driven development runtime; the RAB-1 prospective contract registers exactly one four-variant family |
| 103 | Implemented independent finite-program statistics and separately founder-authorized protected progression; RAB-1 registers one adapter and evaluator, with no result or protected opening yet |
| 104 | Observe approved candidates on current data without exchange orders |
| 105 | Add durable paper execution, accounting, and reconciliation |
| 106 | Govern portfolio allocation, exposure, drawdown, leverage, and kill switches independently |
| 107 | Isolate exchange connectivity and restricted credentials behind independent risk checks |
| 108 | Consider a manually activated, severely limited tiny-capital pilot only after independent approval |
| 109 | Connect research, validation, observation, deployment, reduction, and retirement under separate bounded controls |

## Repository layout

The parts most useful for review are:

```text
contracts/                 versioned authority and machine contracts
docs/                      current documentation, historical records and evidence maps
offchain/                  research, custody, governance and projection code
offchain/tests/            deterministic verification suite
web/                       public observer, founder Worker and research engine
scripts/                   supported local operator/verification tooling
```

The [documentation home](docs/README.md) distinguishes current documents from historical, superseded, design-only, immutable-evidence, and machine-reference material. That distinction is important in a repository with a long research history: an old document can be historically correct without being current authority.

## Public review and rights

This repository is visible for portfolio demonstration, inspection, and professional review. It is not open source, and public visibility does not grant general permission to use, copy, modify, redistribute, deploy, host, or commercialize it. See the [LICENSE](LICENSE) for the concise terms and contact address.

## Running the tests

The repository does not currently document a verified fresh-clone bootstrap for the complete test environment. For an already configured checkout with the ignored local virtual environment at `offchain/.venv`, run:

```bash
env -u PYTHONPATH \
PYTHONDONTWRITEBYTECODE=1 \
offchain/.venv/bin/python -m pytest \
  -p no:cacheprovider \
  offchain/tests \
  -q
```

The virtual environment is local and ignored; it is not included in a fresh clone.

The web and founder surfaces have an independent locked Node dependency graph:

```bash
cd web
npm run install:locked-safe
npm run check
```

That check covers the static observer, authenticated founder routes, research API, data collectors, deterministic metrics, D1 schema, security boundaries, and Cloudflare Worker dry run.

## Documentation

- [Documentation home](docs/README.md)
- [Final project report](docs/DELTAGRID_FINAL_PROJECT_REPORT.md)
- [Final freeze](docs/DELTAGRID_FINAL_FREEZE.md)
- [Current research policy](docs/RESEARCH_POLICY.md)
- [Current risk policy](docs/RISK_POLICY.md)
- [Current safety invariants](docs/SAFETY_INVARIANTS.md)
- [Evidence summaries](docs/research-summaries/README.md)
- [Operator guide](docs/OPERATOR_GUIDE.md)
- [Forward Market Data Acquisition](docs/DELTAGRID_FORWARD_MARKET_DATA_ACQUISITION.md)
- [Mission 101 Research Reopening Governance](docs/DELTAGRID_RESEARCH_REOPENING_GOVERNANCE.md)
- [Mission 102 Development Research Runtime](docs/DELTAGRID_DEVELOPMENT_RESEARCH_RUNTIME.md)
- [Mission 103 Independent Statistical and Protected-Evidence Governance](docs/DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE.md)
- [P1.1 Public Projection](docs/DELTAGRID_PUBLIC_PROJECTION.md)
- [Documentation registry](docs/documentation-status.json)

<details>
<summary>Historical compatibility notes</summary>

These markers are retained for historical documentation verification. They describe earlier repository phases and do not override the current project status above.

Committed pre-freeze evidence records 37 passing Alpha Search B/reset focused tests and 715 passing complete off-chain tests, with one third-party `websockets.legacy` deprecation warning. These are historical pre-freeze baselines, not the full-suite total at the published final freeze.

<!-- MISSION-84-CLOSURE:START -->
### Mission 84 Closure

Mission 84 closed its deterministic synthetic-fixture pipeline with zero real-data validated alpha candidates. The historical fixture-screening records remain preserved but authorize no model training, strategy promotion, live signal, order, capital, or profitability claim. There is no Mission 84.9.
<!-- MISSION-84-CLOSURE:END -->

<!-- MISSION-85-CHARTER:START -->
### Mission 85 Crypto Funding-Carry Research Charter

Mission 85 locked a falsification-first funding-carry charter before real-market collection. It did not prove profitability and prohibited ML rescue, live trading, orders, and capital. Its next authorized data-only phase was Mission 86 Real-Market Data Foundation.
<!-- MISSION-85-CHARTER:END -->

<!-- MISSION-86-DATA-FOUNDATION:START -->
### Mission 86 Real-Market Data Foundation

Mission 86 implemented public-data acquisition, normalization, provenance, and deterministic manifests. It performed no strategy backtest or profitability analysis. Its output remained `UNCERTIFIED_PENDING_MISSION87` until Mission 87 Dataset Certification and Quality Gate.
<!-- MISSION-86-DATA-FOUNDATION:END -->

<!-- MISSION-87-CERTIFICATION:START -->
### Mission 87 Dataset Certification and Quality Gate

Mission 87 certified structural data quality and lineage. It performed no strategy backtest or holdout performance evaluation. The next historical phase was Mission 88 Execution and Cost Reality Model.
<!-- MISSION-87-CERTIFICATION:END -->

<!-- MISSION-88-COST-MODEL:START -->
### Mission 88 Execution and Cost Reality Model

Mission 88 completed an assumption-bounded cost model with no strategy backtest and no order-book precision claim. Its next historical phase was Mission 89 Baseline Strategy Falsification.
<!-- MISSION-88-COST-MODEL:END -->

</details>
