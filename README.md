# DeltaGrid

DeltaGrid is a Python-based quantitative research and operations system built to
falsify cryptocurrency trading ideas before they can reach real capital. It
combines market-data validation, event-driven simulation, realistic execution
costs, risk controls, statistical testing, reproducible evidence, durable local
orchestration, and a read-only founder cockpit.

The long-term goal is a private quantitative investment operating system that
can discover, test, validate, observe, deploy, monitor, and retire strategies
for its owner's capital. It should become increasingly autonomous in research
and routine operations, but it must never be able to expand its own authority,
weaken risk controls, open protected data early, or promote itself directly into
trading.

## Current status

There is **no validated profitable strategy**, no selected candidate, no current
paper-trading authorization, no live-trading authorization, and no capital
deployment.

The final research freeze remains controlling for strategy research and trading.
Later contracts authorized a narrow backend programme only: research admission,
synthetic control execution, canonical evidence, read-only system projection, a
loopback-only cockpit, and one durable observation workflow. Those components
do not establish alpha and do not authorize market research, model training,
orders, exchange access, credentials, or capital.

The current published backend chain ends at Mission 97 commit
`8afa19a06dd6f1b100befce067107c1fa347d471`. Its full repository suite passed
1,153 tests with one third-party `websockets.legacy` deprecation warning.

The final project freeze was published in commit
`ce82c5b887a08185b7acceb35480783d02eb0b5d`. None of the tested strategies met
the promotion standard. That negative result is not a profitability success.
The engineering success is that DeltaGrid rejected weak hypotheses instead of
overfitting or deploying them.

## Why I built it

Most trading projects begin with indicators and end with a profitable-looking
backtest. I wanted to build the process in the opposite order: define the
hypothesis, freeze the rules, verify the data, account for costs, test
chronologically, and reject the strategy when the evidence is weak.

The broader goal is to encode the work of a private quantitative investment
company into separate, auditable software responsibilities:

- research proposes and falsifies ideas;
- data services preserve provenance and reproducibility;
- validation independently challenges surviving candidates;
- risk governs exposure and capital;
- execution places and reconciles orders only after approval;
- operations detects failures and recovers safely;
- the founder cockpit explains what happened and why.

Self-advancing must never mean self-authorizing.

## What exists today

### Research and falsification foundation

DeltaGrid includes:

- public crypto-data acquisition with provenance records;
- deterministic dataset certification for BTC, ETH, and SOL research data;
- causal features and event-driven strategy simulation;
- normal, conservative, and severe execution-cost assumptions;
- drawdown, exposure, concentration, and risk controls;
- chronological development, validation, and sealed holdout boundaries;
- null controls and Holm multiple-testing correction;
- versioned contracts, evidence files, and SHA-256 identities;
- historical Freqtrade parity infrastructure, without current strategy or
  trading authorization.

### Governed backend chain

| Mission | Component | Current role |
|---|---|---|
| 93 | Research Cockpit v0 charter | Audited the repository and froze the missing backend interfaces before UI work |
| 94 | Research Admission Core | Registers budgets, reserves immutable trials, resolves permitted synthetic datasets, and fails closed |
| 95 | Canonical Result Engine Service | Executes exactly admitted synthetic non-alpha controls and publishes independently verifiable results |
| 96A | Research Control Plane | Reads the research ledger and verified results without writing or recalculating them |
| 96B | Research Cockpit v0 | Presents local read-only snapshots in a secure loopback-only browser interface |
| 97 | Durable Observation Orchestrator | Progresses one fixed observation workflow with leases, fencing, bounded retries, recovery, and immutable manifests |

## Current architecture

```text
Governance contracts
        ↓
Research admission and immutable trial lifecycle
        ↓
Deterministic synthetic control execution
        ↓
Canonical result bundles and independent verification
        ↓
Read-only control-plane snapshots
        ↓
Founder cockpit
        ↓
Durable observation orchestration and recovery
```

This is a controlled observation and evidence loop. It is not yet the complete
strategy lifecycle.

The future operating loop is intended to become:

```text
Observe evidence and system state
        ↓
Propose a bounded economic hypothesis
        ↓
Preregister data, costs, budget, and rejection rules
        ↓
Run development research
        ↓
Reject weak ideas
        ↓
Independently validate survivors
        ↓
Shadow and paper operation
        ↓
Independent portfolio-risk approval
        ↓
Tightly bounded capital deployment
        ↓
Monitor, reduce, suspend, or retire
```

## Research completed

| Research area | Outcome |
|---|---|
| Synthetic benchmark pipeline | Infrastructure completed; no real-market validated alpha |
| Funding and basis carry | Rejected |
| Directional strategies | Rejected |
| Macro-regime hypothesis | Rejected before strategy construction |
| Trade-flow and lead-lag hypotheses | Rejected in development |

Alpha Search B was rejected on development data without opening validation or
holdout. Its committed publication evidence records zero scoped validation
access and zero scoped holdout access.

The detailed timeline, candidate results, statistical controls, and decision
evidence are in the
[Final Project Report](docs/DELTAGRID_FINAL_PROJECT_REPORT.md).

## Future milestones

These milestones describe the intended engineering sequence. They are planning
direction, not implementation authority. Every stage requires its own reviewed,
versioned contract before it may access data, execute research, trade, or use
capital.

| Planned milestone | Purpose | Required proof before advancing |
|---|---|---|
| Mission 98 — Autonomous Research Director | Select the next permitted research action from fixed evidence and policy inputs | It can advance or stop research without rescuing rejected ideas or expanding its authority |
| Mission 99 — Current Data Fabric | Build reproducible, certified, continuously maintained market datasets | Every experiment can be reproduced from exact data, provenance, and availability timing |
| Mission 100 — General Research Runtime | Provide one trusted event-driven runtime for registered strategies, controls, costs, and risk models | New hypotheses do not require mission-specific accounting or backtest engines |
| Mission 101 — Independent Validation Governor | Enforce development, validation, holdout, replication, and multiple-testing gates | A candidate cannot influence or approve its own examination |
| Mission 102 — Real-Time Shadow Runtime | Run approved candidates on current data without exchange orders | Signals remain causal, stable, and operational outside historical backtests |
| Mission 103 — Paper Execution and Reconciliation | Maintain durable paper orders, fills, positions, costs, funding, and reconciliation | Long-running execution and accounting remain correct through interruptions and incidents |
| Mission 104 — Portfolio and Risk Governor | Control allocation, exposure, concentration, drawdown, leverage, and kill switches independently of strategies | No strategy can directly choose its own capital or disable portfolio limits |
| Mission 105 — Exchange Gateway and Credential Boundary | Isolate exchange connectivity, restricted keys, pre-trade checks, idempotent orders, and reconciliation | Exchange access cannot bypass the independent risk governor |
| Mission 106 — Tiny-Capital Pilot | Operate one approved candidate on one venue with severe limits and manual activation | Real-money operational correctness is demonstrated before any scale discussion |
| Mission 107 — Autonomous Strategy Lifecycle | Connect research, validation, shadowing, monitored deployment, reduction, and retirement | DeltaGrid can improve its portfolio without weakening governance |
| Later — Scaling and Resilience | Add redundancy, disaster recovery, multiple strategies, and independently reviewed capital scaling | Control quality grows at least as fast as operational and capital complexity |

## Engineering principles

- **Falsification first:** weak ideas should be rejected quickly and preserved as
  negative evidence.
- **Deterministic evidence:** important decisions, inputs, artifacts, and hashes
  must be reproducible.
- **Separation of duties:** research, validation, risk, execution, and authority
  must not collapse into one self-approving component.
- **Fail closed:** uncertain identity, state, data, authority, or recovery must
  stop progression.
- **Bounded autonomy:** the system may automate only explicitly authorized
  actions with budgets, limits, and terminal conditions.
- **Visible failure:** failures should be detected, bounded, recorded, and
  recoverable rather than hidden or retried forever.
- **No authority from software maturity:** code, tests, dashboards, or readiness
  do not establish economic edge or capital permission.

## Engineering highlights

- Python-based research and operations services
- Deterministic, versioned research and implementation contracts
- Causal feature timing and chronological evaluation
- Event-driven execution semantics
- Explicit fees, spread, slippage, latency, and cost stress
- Sealed validation and holdout boundaries
- Immutable trial, result, workflow, and artifact identities
- Loopback-only founder cockpit with no write endpoints
- Durable SQLite orchestration with append-only events, leases, fencing,
  bounded retries, cancellation, and crash recovery
- Historical Freqtrade parity infrastructure; lookahead, recursive, and other
  bias analyses remain future gates
- 731 passing automated tests in the full suite at the published final freeze;
  the Mission 97 publication passed 1,153 tests
- Reproducible evidence and checksum manifests

Passing tests verify implementation and repository invariants. They are not
evidence that a strategy is profitable.

## Repository structure

```text
contracts/       Research, safety, implementation, and freeze contracts
offchain/        Data, simulation, research, orchestration, and test code
docs/            Architecture, decisions, policies, guides, and reports
docs/evidence/   Tracked research evidence and checksum manifests
scripts/         Verification and operator-development utilities
```

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

## Limitations and safety

- There is no validated profitable strategy, no live orders, no current
  paper-trading authorization, and no capital deployment.
- Mission 97 observes and records state; it does not authorize autonomous
  research or autonomous trading.
- Cost, slippage, latency, and market-impact models contain assumptions and
  cannot reproduce every live-market condition.
- Backtests and statistical tests do not guarantee future results.
- Future research requires a new versioned reopening contract before any
  data-driven strategy work begins.
- No historical paper, AI, readiness, or autonomous component overrides current
  contracts.
- Test success verifies tested properties only; it does not establish alpha.
- No Alpha Search B candidate was authorized for Freqtrade translation.

The Alpha Search B rejection was published in commit
`a31f4da4fc8b52ca2fa6aaad697350d6e9180736`. That commit is the historical
research base, **not a permanent assertion about every future repository
HEAD**. The later commit `ce82c5b887a08185b7acceb35480783d02eb0b5d`
published the final project freeze.

## Documentation

- [Documentation home](docs/README.md)
- [Final Project Report](docs/DELTAGRID_FINAL_PROJECT_REPORT.md)
- [Final Freeze Explanation](docs/DELTAGRID_FINAL_FREEZE.md)
- [Future Strategy Intake Policy](docs/FUTURE_STRATEGY_INTAKE_POLICY.md)
- [Research Cockpit v0 Charter](docs/DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md)
- [Research Admission Core](docs/DELTAGRID_RESEARCH_ADMISSION_CORE.md)
- [Canonical Result Engine Service](docs/DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE.md)
- [Research Control Plane](docs/DELTAGRID_RESEARCH_CONTROL_PLANE.md)
- [Research Cockpit v0](docs/DELTAGRID_RESEARCH_COCKPIT_UI.md)
- [Durable Observation Orchestrator](docs/DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR.md)
- [Final Freeze Contract](contracts/DELTAGRID_FINAL_FREEZE_V1.json)
- [Final Freeze Evidence](docs/evidence/deltagrid_final_freeze/FINAL_FREEZE_VERIFICATION.json)

## Author

Built by Tushar Rawat as an independent quantitative research and
software-engineering project.

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
and no order-book precision claim. Its next historical phase was Mission 89
Baseline Strategy Falsification.
<!-- MISSION-88-COST-MODEL:END -->

</details>
