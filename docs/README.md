# DeltaGrid documentation

This page is the navigation entrance to DeltaGrid's documentation. It separates
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
  `STOP_REPOSITORY_INTERFACE_GAPS_FOUND` decision. That charter does not authorize a
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
- [Autonomous Research Director v1](DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR.md)
  documents Mission 98's deterministic evidence verification, fixed
  recommendation policy, independent verifier, and append-only decision
  ledger. A recommendation is not authority and Mission 98 performs no
  research.
- [Autonomy constitution v1](DELTAGRID_AUTONOMY_CONSTITUTION.md) fixes founder
  root authority, separates proposals from activation, and permanently
  prohibits self-authorization.
- [Temporal Market Data Control Plane v1](DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE.md)
  documents Mission 99's immutable revision-aware releases, independent
  certification, legacy metadata audit, recovery classification, and
  synthetic-only as-of resolver.
- [Autonomy constitution v2](DELTAGRID_AUTONOMY_CONSTITUTION_V2.md) records
  the founder-approved authority change for bounded unauthenticated public
  market-data collection only.
- [Forward Market Data Acquisition](DELTAGRID_FORWARD_MARKET_DATA_ACQUISITION.md)
  documents Mission 100 forward capture, raw evidence, receipt time, clock
  checks, revisions, checkpoints, local backup verification, the first-live
  remediation, and the successful controlled production activation.
- [Research Reopening Governance](DELTAGRID_RESEARCH_REOPENING_GOVERNANCE.md)
  documents Mission 101's independently verified backup bridge, distinct
  forward-custody profile, mixed-stream latest-causal-revision development
  descriptors, private finite permits with observed clean-repository binding,
  trusted write times and global append-only capacity, independently observed
  repository identity for metadata-only Admission V2, and causal permit
  revocation. It authorizes no
  result-bearing execution.
- [Development Research Runtime](DELTAGRID_DEVELOPMENT_RESEARCH_RUNTIME.md)
  documents Mission 102's exact consumed-permit binding, immutable one-trial
  execution specification, sealed future-extensible registry, causal selected
  value loader, deterministic accounting, independent replay, and atomic
  Mission 94 completion. Its registry began empty; RAB-1 now prospectively
  authorizes exactly one four-variant family.
- [Independent statistical and protected-evidence governance](DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE.md)
  documents Mission 103's campaign-level anti-reset admission, exact
  program-wide empirical statistics and Holm correction, one fixed candidate,
  prospective protected partitions, metadata-only materialization, and durable
  one-use founder-authorized protected openings. The prospective RAB-1
  contract authorizes one exact adapter and evaluator without starting Mission 104.
- [Mission-104 readiness lock](M104_READINESS_LOCK.md) records the only active
  prospective RAB-1 programme, its 180-day forward calendar, exact gates, and
  `NONE` authority boundary.
- [RAB-1 overlap decision](RAB1_OVERLAP_DECISION.md) records the pre-value
  lineage decision and the contradiction stop condition.


- [Platform P1.1 public projection](DELTAGRID_PUBLIC_PROJECTION.md) documents
  the deterministic repository-only public projection boundary, canonical
  package and independent verifier. It opens no private runtime or market
  values and has authority effect `NONE`.
These documents answer different questions. The root README is living
documentation and the public overview; the final freeze controls strategy
research and trading status; the intake policy governs possible future
proposals; and the Mission 93–103 records describe the narrow backend components
implemented after the freeze.

## Current project state

DeltaGrid's research infrastructure is complete, but the completed research did
not find a validated profitable strategy. No candidate is selected. Alpha
discovery has stopped under the final freeze. Paper trading, live trading,
exchange access, credential access, and capital deployment are not authorized.

The final freeze remains controlling for result-bearing research and trading.
Engineering continued only through separately versioned contracts that built a
research admission boundary, deterministic synthetic control execution,
canonical evidence, read-only system projection, a local cockpit, and a durable
observation workflow.

The current backend chain ends at Mission 103. Mission 98 remains deterministic
and decision-only. Mission 99 adds data custody without authorizing network
collection or real-data research resolution. Mission 100 separately authorizes
only bounded unauthenticated public-market collection into a private acquisition
journal; it does not reopen strategy research or make that evidence research
admissible without Mission 101's separate verified bridge, exact descriptor,
and applicable permit. Mission 101 adds those governance and admission
mechanisms but stops before result-bearing execution. Passing tests verify
software and repository properties; they do not establish alpha or capital
authority. Mission 102 permits only an exact Mission 101 admitted development
trial to execute through its consumed permit slot. The production registry
initially has no economic family, and no real Mission 102 research was executed
during implementation. No Mission 103 campaign, program, candidate,
materialization, authorization, or protected execution was created during
implementation; its statistical-adapter and protected-evaluator registries
both have zero production entries. Validation and holdout remain closed until
exact future founder authorizations, and a maximum M103 verdict has authority
effect `NONE`. ML, paper/live
trading, exchanges, credentials, orders, and capital remain unauthorized.

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

The major superseded documents listed below now carry visible status banners.
`ARCHITECTURE_STATE.md` and `MISSION_INDEX.md` are visibly marked historical,
all ADRs are visibly marked as historical decisions, and
`DELTA_AUTONOMY_ARCHITECTURE.md` is visibly marked design-only. These banners
clarify present authority without changing the preserved historical or design
bodies.

## Understand the current system

Begin with the [project overview](../README.md), then read the
[final project report](DELTAGRID_FINAL_PROJECT_REPORT.md) for the completed
research programme and its negative economic result.

The current backend architecture is the Mission 93–103 chain:

| Mission | Document | Responsibility |
|---|---|---|
| 93 | [Research Cockpit v0 charter](DELTAGRID_RESEARCH_COCKPIT_V0_CHARTER.md) | Identified the missing application, dataset, ledger, control, and result interfaces before presentation work |
| 94 | [Research Admission Core](DELTAGRID_RESEARCH_ADMISSION_CORE.md) | Controls budgets, immutable trial reservations, permitted synthetic datasets, and exact non-alpha controls |
| 95 | [Canonical Result Engine Service](DELTAGRID_CANONICAL_RESULT_ENGINE_SERVICE.md) | Executes admitted synthetic controls and publishes independently verifiable result bundles |
| 96A | [Research Control Plane](DELTAGRID_RESEARCH_CONTROL_PLANE.md) | Produces read-only system, trial, result, and incident projections without recalculating evidence |
| 96B | [Research Cockpit](DELTAGRID_RESEARCH_COCKPIT_UI.md) | Presents Mission 96A snapshots through a loopback-only single-user browser interface |
| 97 | [Durable Observation Orchestrator](DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR.md) | Progresses one fixed observation workflow with durable state, bounded retries, fencing, recovery, and immutable manifests |
| 98 | [Autonomous Research Director](DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR.md) | Verifies Mission 97 evidence and selects one independently verified, non-executable recommendation |
| 99 | [Temporal Market Data Control Plane](DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE.md) | Custodies immutable, revision-aware releases; independently certifies them; audits legacy metadata; and resolves only authorized synthetic evidence as of a decision time |
| 100 | [Forward Market Data Acquisition](DELTAGRID_FORWARD_MARKET_DATA_ACQUISITION.md) | Collects only frozen public Binance market data into a private append-only forward-evidence journal with clock, retry, revision, checkpoint, and backup controls |
| 101 | [Research Reopening Governance](DELTAGRID_RESEARCH_REOPENING_GOVERNANCE.md) | Verifies immutable Mission 100 backups, certifies distinct forward custody, binds exact development datasets and permits, and performs metadata-only development admission without execution |
| 102 | [Development Research Runtime](DELTAGRID_DEVELOPMENT_RESEARCH_RUNTIME.md) | Executes only an exact consumed-permit-bound development trial and independently replays and finalizes its evidence; RAB-1 prospectively registers one family |
| 103 | [Independent statistical and protected-evidence governance](DELTAGRID_INDEPENDENT_RESEARCH_VALIDATION_GOVERNANCE.md) | Prevents campaign/program multiplicity reset, applies exact program-wide statistics, freezes at most one candidate, and governs prospective one-use protected stages; production adapter and evaluator counts are zero |

| P1.1 | [Public Projection](DELTAGRID_PUBLIC_PROJECTION.md) | Exports and independently verifies a deterministic repository/public-contract projection without opening private runtimes, market values, protected data, network access, or trading authority |

[Architecture State](ARCHITECTURE_STATE.md) remains a cumulative historical
record of mission-era architecture. It is useful for tracing how earlier
components appeared, but it is not the current architecture authority and does
not authorize those components to operate.

The final project report is preserved evidence from the freeze publication. It
should be read alongside the living root README, the final freeze, and the
Mission 93–103 implementation contracts.

## Planned direction

Platform P1.1 is a separate non-authorizing productization boundary. It does not consume Mission 104, which remains reserved for observation of an actually qualified candidate.

Mission 103's implemented status and the provisional Mission 104–109 roadmap
appear once, in the
[root README](../README.md#mission-103-status-and-provisional-roadmap-missions-104109).
The remaining roadmap is planning direction rather than authorization.

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
  verification record, its historical checksum manifest, and exact publication
  snapshots of the root README and final-freeze verification test.

Contracts and evidence intentionally use formal machine status codes, exact
hashes, counters, identities, and deterministic formatting. They should not be
conversationally rewritten. Companion summaries explain them without replacing
or silently reinterpreting the raw records. They do not reopen research or
change any authorization; exact historical facts remain controlled by the
linked contracts and evidence.

Because the root README is living documentation, its final-freeze publication
bytes are preserved separately as
[`README.final-freeze-publication.txt`](evidence/deltagrid_final_freeze/README.final-freeze-publication.txt).
The publication-era freeze test is likewise preserved as
[`test_deltagrid_final_freeze.final-freeze-publication.py.txt`](evidence/deltagrid_final_freeze/test_deltagrid_final_freeze.final-freeze-publication.py.txt).
These immutable snapshots retain the two historical identities recorded in the
publication manifest; the living files may change without rewriting that
evidence.

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

The [operator guide](OPERATOR_GUIDE.md) documents the two supported current
local development and verification commands:
`scripts/mission_control.py` and `scripts/mission_pack_runner.py`. It explains
safe dry-run use, local logs, repository actions, and failure handling. Public
docstrings for those supported operator modules are also current. The guide
does not authorize research or trading. Those utilities are not the Mission 97
orchestrator.

Mission 97's separate bounded foreground commands are documented in the
[Durable Observation Orchestrator guide](DELTAGRID_DURABLE_WORKFLOW_ORCHESTRATOR.md).
They progress one fixed read-only observation workflow and expose no arbitrary
command, plugin, background scheduler, research, or trading interface.

Mission 98's separate decision-only commands are documented in the
[Autonomous Research Director guide](DELTAGRID_AUTONOMOUS_RESEARCH_DIRECTOR.md).
They preview, record, inspect, and verify recommendations; they do not execute
the recommended work or change any authorization.

The current local verification CLIs and the plain-text command logs they produce
have been reviewed for clear human-facing language. Their machine-readable JSON,
contracts, and evidence remain unchanged. A successful command or generated report
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

When historical documents conflict with the final freeze, the final freeze controls.

Later Mission 93–99 contracts control only the narrow backend capabilities they
explicitly authorize.
