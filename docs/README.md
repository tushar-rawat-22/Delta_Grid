# DeltaGrid documentation

This page is the entrance to DeltaGrid's documentation. It separates the
documents that describe the project today from historical decisions, future
designs, immutable research evidence, and machine-oriented records.

DeltaGrid contains a long engineering and research history. A document may be
accurate about the phase in which it was written without describing what is
authorized now.

## Start here

- [Project overview](../README.md) explains DeltaGrid's goal, current
  architecture, completed research, present authority, and planned milestone
  sequence for a general reader.
- [Final freeze](DELTAGRID_FINAL_FREEZE.md) explains why result-bearing research
  stopped and defines the controlling strategy and trading boundary.
- [Future strategy intake policy](FUTURE_STRATEGY_INTAKE_POLICY.md) defines the
  gate a genuinely new proposal must pass before new research can begin.
- [ML research adapter](DELTAGRID_ML_RESEARCH_ADAPTER.md) records a possible
  future design policy. It does not authorize implementation or model training.
- [Research Cockpit v0 charter](DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md)
  records the read-only interface audit and its
  `STOP_REPOSITORY_INTERFACE_GAPS_FOUND` decision. It did not itself authorize a
  dashboard, research, protected-data access, or trading.
- [Research Admission Core](DELTAGRID_RESEARCH_ADMISSION_CORE.md) documents the
  synthetic-only, no-execution gate authorized by the Mission 94 contract.
- [Canonical Result Engine Service](DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE.md)
  documents Mission 95's deterministic execution and canonical result boundary
  for exactly admitted synthetic non-alpha controls.
- [Research Control Plane v1](DELTAGRID_RESEARCH_CONTROL_PLANE.md) documents
  Mission 96A's read-only ledger, verified-result projection, and integrity
  incident boundary.
- [Research Cockpit v0](DELTAGRID_RESEARCH_COCKPIT_UI.md) documents Mission
  96B's loopback-only, single-user browser presentation over Mission 96A. It
  adds no research, accounting, risk, validation, execution, or trading logic.
- [Durable Observation Orchestrator v1](DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR.md)
  documents Mission 97's one fixed local foreground observation workflow,
  durable event history, leases, recovery, and immutable artifacts. It adds no
  research, market, model, trading, exchange, autonomous-trading, or capital
  authority.

These documents answer different questions. The root README is the public
overview; the final freeze controls strategy research and trading status; the
intake policy governs possible future proposals; and the Mission 93–97 records
define the narrow backend components implemented after the freeze.

## Current project state

DeltaGrid's research infrastructure is complete, but the completed research did
not find a validated profitable strategy. No candidate is selected. Paper
trading, live trading, exchange access, and capital deployment are not
authorized.

The final freeze remains controlling for result-bearing research and trading.
Engineering continued only through separately versioned contracts that built a
research admission boundary, deterministic synthetic control execution,
canonical evidence, read-only system projection, a local cockpit, and a durable
observation workflow.

The current published backend chain ends at Mission 97 commit
`8afa19a06dd6f1b100befce067107c1fa347d471`. The complete repository suite at
that publication passed 1,153 tests with one third-party
`websockets.legacy` deprecation warning. Passing tests verify software and
repository properties; they do not establish alpha or capital authority.

New strategy work still requires a new versioned reopening contract before
implementation or result-bearing research begins.

## Documentation status labels

The [documentation registry](documentation-status.json) assigns one label to
each audited document:

- **CURRENT_PUBLIC** — current material written for public readers.
- **CURRENT_INTERNAL** — current engineering, research, risk, or operator
  guidance.
- **HISTORICAL** — a preserved record of an earlier project phase.
- **SUPERSEDED** — a historical document replaced by a newer controlling
  document.
- **DESIGN_ONLY** — a possible future design that is not implemented or
  authorized by the document alone.
- **EVIDENCE_IMMUTABLE** — human-readable research or audit evidence whose
  historical wording should be preserved.
- **MACHINE_REFERENCE** — a deterministic contract, manifest, configuration,
  or other primarily machine-oriented record.

A status label describes how to read a file. It does not erase the file's
history or alter the result it records.

The major superseded documents listed below carry visible status banners.
`ARCHITECTURE_STATE.md` and `MISSION_INDEX.md` are marked historical, all ADRs
are marked as historical decisions, and `DELTA_AUTONOMY_ARCHITECTURE.md` is
marked design-only. These banners clarify present authority without changing
the preserved historical or design bodies.

## Understand the current system

Begin with the [project overview](../README.md), then read the
[final project report](DELTAGRID_FINAL_PROJECT_REPORT.md) for the completed
research programme and its negative economic result.

The current backend architecture is the Mission 93–97 chain:

| Mission | Document | Responsibility |
|---|---|---|
| 93 | [Research Cockpit v0 charter](DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md) | Identified the missing application, dataset, ledger, control, and result interfaces before presentation work |
| 94 | [Research Admission Core](DELTAGRID_RESEARCH_ADMISSION_CORE.md) | Controls budgets, immutable trial reservations, permitted synthetic datasets, and exact non-alpha controls |
| 95 | [Canonical Result Engine Service](DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE.md) | Executes admitted synthetic controls and publishes independently verifiable result bundles |
| 96A | [Research Control Plane](DELTAGRID_RESEARCH_CONTROL_PLANE.md) | Produces read-only system, trial, result, and incident projections without recalculating evidence |
| 96B | [Research Cockpit](DELTAGRID_RESEARCH_COCKPIT_UI.md) | Presents Mission 96A snapshots through a loopback-only single-user browser interface |
| 97 | [Durable Observation Orchestrator](DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR.md) | Progresses one fixed observation workflow with durable state, bounded retries, fencing, recovery, and immutable manifests |

The operating chain is:

```text
Governance contracts
        ↓
Admission and immutable trial history
        ↓
Deterministic synthetic execution
        ↓
Canonical evidence and verification
        ↓
Read-only control-plane snapshots
        ↓
Founder cockpit
        ↓
Durable observation orchestration
```

This is an observation and evidence system. It is not yet an autonomous research
or trading system.

[Architecture State](ARCHITECTURE_STATE.md) remains a cumulative historical
record of mission-era architecture. It is useful for tracing how earlier
components appeared, but it is not the current architecture authority and does
not authorize those components to operate.

The final project report is preserved evidence from the freeze publication. It
should be read alongside the current status in the root README, the final
freeze, and the Mission 93–97 implementation contracts.

## Planned direction

The long-term goal is a private quantitative investment operating system that
can discover, test, validate, observe, deploy, monitor, and retire strategies
for its owner's capital. Increasing autonomy must remain subordinate to fixed
governance, independent validation, risk limits, and human-controlled capital
authority.

The planned milestone sequence is:

1. **Mission 98 — Autonomous Research Director:** choose the next permitted
   research action from evidence, budgets, incidents, and fixed policy.
2. **Mission 99 — Current Data Fabric:** maintain reproducible, certified,
   availability-aware market datasets.
3. **Mission 100 — General Research Runtime:** provide one trusted event-driven
   runtime for registered strategies, controls, costs, and risk models.
4. **Mission 101 — Independent Validation Governor:** enforce development,
   validation, holdout, replication, and multiple-testing gates independently
   of candidate construction.
5. **Mission 102 — Real-Time Shadow Runtime:** evaluate approved candidates on
   current data without exchange orders.
6. **Mission 103 — Paper Execution and Reconciliation:** maintain durable paper
   orders, fills, positions, funding, costs, and reconciliation.
7. **Mission 104 — Portfolio and Risk Governor:** control allocation, exposure,
   concentration, drawdown, leverage, and kill switches independently of
   strategies.
8. **Mission 105 — Exchange Gateway and Credential Boundary:** isolate restricted
   exchange access behind pre-trade risk checks and reconciliation.
9. **Mission 106 — Tiny-Capital Pilot:** operate one independently approved
   candidate on one venue with severe limits and manual activation.
10. **Mission 107 — Autonomous Strategy Lifecycle:** connect governed research,
    validation, shadowing, monitored deployment, reduction, and retirement.

These numbers are planning labels, not authorization. Each milestone requires a
separate reviewed contract. A roadmap does not grant data access, research,
model, exchange, paper, live, autonomous-trading, or capital permission.

## Current policies

- [Research policy](RESEARCH_POLICY.md)
- [Risk policy](RISK_POLICY.md)
- [Safety invariants](SAFETY_INVARIANTS.md)
- [Future strategy intake policy](FUTURE_STRATEGY_INTAKE_POLICY.md)

The first three are current internal policies aligned with the final freeze.
They explain the research, risk, and authorization controls that apply today
without expanding any authorization. The future strategy intake policy is the
current gate for considering genuinely new work.

## Research history

The following records explain how DeltaGrid reached its final research result.
They are historical records, not current permission to resume a programme or
perform a listed next action.

- [Product reset](DELTAGRID_PRODUCT_RESET.md) changed the project from
  open-ended infrastructure growth to a finite falsification programme.
- [Mission 89 baseline falsification](MISSION89_BASELINE_FALSIFICATION.md)
  records the funding and basis carry rejection.
- [Mission 90 directional tournament](MISSION90_DIRECTIONAL_TOURNAMENT.md)
  records the directional-strategy rejection.
- [Mission 91 hypothesis record](MISSION_91_NEW_ECONOMIC_HYPOTHESIS_DISCOVERY.md)
  freezes the later session-conditional hypothesis.
- [Mission 92 session-premium falsification](MISSION_92_SESSION_PREMIUM_FALSIFICATION.md)
  records that hypothesis's development rejection.
- [Alpha Search A rejection](ALPHA_SEARCH_A_REJECTION.md) records the causal
  data-feasibility failure before strategy construction.
- [Alpha Search B protocol](ALPHA_SEARCH_B_PROTOCOL.md) records the frozen
  protocol that preceded the final development rejection.
- [Final project report](DELTAGRID_FINAL_PROJECT_REPORT.md) consolidates the
  research timeline, negative results, controls, and evidence references.

Historical next steps in these files have been overtaken by later evidence and
the final freeze.

## Architecture decisions

The [ADR directory](ADR/) contains chronological architecture decision records.
They preserve what was accepted during each historical phase, including the
reasoning and boundaries used at the time.

An ADR status of `Accepted` means that the decision was accepted in that phase.
It does not mean that the work is currently authorized, operational, or part of
the present project plan.

## Raw contracts and evidence

- [Research and evidence summaries](research-summaries/README.md) provide
  plain-English companions to the preserved research records below.
- [Contracts](../contracts/) contain deterministic research, safety,
  implementation, and freeze records.
- [Evidence](evidence/) contains committed research and verification records.
- [Alpha Search B development evidence](evidence/alpha_search_b_development/)
  contains the raw development publication and checksum manifest.
- [Final-freeze evidence](evidence/deltagrid_final_freeze/) contains the freeze
  verification record and its checksum manifest.

Contracts and evidence intentionally use formal machine status codes, exact
hashes, counters, identities, and deterministic formatting. They should not be
conversationally rewritten. Companion summaries explain them without replacing
or silently reinterpreting the raw records. They do not reopen research or
change any authorization; exact historical facts remain controlled by the
linked contracts and evidence.

## Superseded and design-only material

The following documents are retained for history but have been superseded:

- [Charter](CHARTER.md)
- [Product reset](DELTAGRID_PRODUCT_RESET.md)
- [Autonomous bot roadmap](DELTA_AUTONOMOUS_BOT_ROADMAP.md)
- [Mission 58 documentation registry](DOCUMENTATION_REGISTRY.md)
- [Institutional alpha research plan](INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md)
- [Project source of truth](PROJECT_SOURCE_OF_TRUTH.md)
- [Mission roadmap](ROADMAP.md)
- [Strategy research roadmap](STRATEGY_RESEARCH_ROADMAP.md)

These documents describe possible future designs rather than current authority:

- [Autonomy architecture](DELTA_AUTONOMY_ARCHITECTURE.md)
- [ML research adapter](DELTAGRID_ML_RESEARCH_ADAPTER.md)

These classifications do not delete or invalidate historical content. They tell
readers which material must not be interpreted as the current plan.

## Current operator guidance

Use the [root README test instructions](../README.md#running-the-tests) for an
already configured checkout. The repository does not currently claim a verified
fresh-clone bootstrap for the complete test environment.

The [operator guide](OPERATOR_GUIDE.md) documents the two supported repository
development and verification utilities in `scripts/`. It explains safe dry-run
use, local logs, repository actions, and failure handling. Those utilities are
not the Mission 97 orchestrator and do not authorize research or trading.

Mission 97's separate bounded foreground commands are documented in the
[Durable Observation Orchestrator guide](DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR.md).
They progress one fixed read-only observation workflow and expose no arbitrary
command, plugin, background scheduler, research, or trading interface.

The current local verification CLIs and the plain-text command logs they produce
have been reviewed for clear human-facing language. Their machine-readable JSON,
contracts, and evidence remain exact. A successful command or generated report
verifies only its stated software checks: it does not establish profitable alpha
or authorize paper trading, live trading, capital deployment, model operation,
or autonomous trading.

## Documentation registry

[documentation-status.json](documentation-status.json) is the complete
machine-readable classification of the approved documentation inventory. It is
intended for validation, tooling, and possible future navigation views, not as a
replacement for human documentation.

## Writing standard

[Documentation style](DOCUMENTATION_STYLE.md) defines how new DeltaGrid
documentation should communicate clearly while preserving machine precision,
research evidence, and authorization boundaries.

## Authority rule

When historical documents conflict with the final freeze, the final freeze
controls strategy research and trading authority. Later Mission 93–97 contracts
control only the narrow backend capabilities they explicitly authorize.
