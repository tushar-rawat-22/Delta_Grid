# DeltaGrid documentation

This page is the entrance to DeltaGrid's documentation. It separates the
documents that describe the project today from historical decisions, future
designs, immutable research evidence, and machine-oriented records.

DeltaGrid contains a long engineering and research history. A document may be
accurate about the phase in which it was written without describing what is
authorized now.

## Start here

- [Project overview](../README.md) explains what DeltaGrid is, what was built,
  and the present result for a general reader.
- [Final freeze](DELTAGRID_FINAL_FREEZE.md) explains why research stopped and
  defines the current authorization boundary.
- [Future strategy intake policy](FUTURE_STRATEGY_INTAKE_POLICY.md) defines the
  gate a genuinely new proposal must pass before new research can begin.
- [ML research adapter](DELTAGRID_ML_RESEARCH_ADAPTER.md) records a possible
  future design policy. It does not authorize implementation or model training.

These four documents answer different questions. The root README is the public
overview; the final freeze controls current project status; the intake policy
governs possible future proposals; and the ML adapter is design-only.

## Current project state

DeltaGrid's research infrastructure is complete, but the research did not find
a validated profitable strategy. No candidate is selected. Paper trading and
live trading are not authorized, and capital deployment is blocked.

Alpha discovery has stopped. New strategy work requires a new versioned
reopening contract before implementation or result-bearing research begins.

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

## Understand the current system

Begin with the [project overview](../README.md), then read the
[final project report](DELTAGRID_FINAL_PROJECT_REPORT.md) for a detailed account
of the implemented research platform and completed research.

A concise, current architecture explanation has not yet been created.
[Architecture State](ARCHITECTURE_STATE.md) is a cumulative historical record of
mission-era architecture. It is useful for tracing how components appeared,
but it is not the current architecture authority and does not authorize those
components to operate.

The final project report is preserved evidence from the freeze publication. It
should be read alongside the current status in the root README and final freeze.

## Current policies

- [Research policy](RESEARCH_POLICY.md)
- [Risk policy](RISK_POLICY.md)
- [Safety invariants](SAFETY_INVARIANTS.md)
- [Future strategy intake policy](FUTURE_STRATEGY_INTAKE_POLICY.md)

The first three are short current internal policies whose wording needs later
alignment with the final freeze. This navigation batch does not change their
content or expand any authorization. The future strategy intake policy is the
current gate for considering genuinely new work.

## Research history

The following records explain how DeltaGrid reached its final result. They are
historical records, not current permission to resume a programme or perform a
listed next action.

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

- [Contracts](../contracts/) contain deterministic research, safety, and freeze
  records.
- [Evidence](evidence/) contains committed research and verification records.
- [Alpha Search B development evidence](evidence/alpha_search_b_development/)
  contains the raw development publication and checksum manifest.
- [Final-freeze evidence](evidence/deltagrid_final_freeze/) contains the freeze
  verification record and its checksum manifest.

Contracts and evidence intentionally use formal machine status codes, exact
hashes, counters, identities, and deterministic formatting. They should not be
conversationally rewritten. A human summary may explain them, but it must never
replace or silently reinterpret the raw record.

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

## Running and verifying DeltaGrid

Use the [root README test instructions](../README.md#running-the-tests) for an
already configured checkout. The repository does not currently claim a verified
fresh-clone bootstrap for the complete test environment.

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
controls.
