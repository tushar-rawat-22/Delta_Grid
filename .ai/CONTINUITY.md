# DeltaGrid AI continuity

This file is a bootstrap guide for a future AI assistant or coding model. It is **not** an authority document and it must never be treated as proof that the repository, CI or production deployment still matches the snapshot described here.

The purpose is simple: a new model should be able to become useful in minutes without asking the founder to reconstruct weeks of work.

## First rule

Before proposing or changing anything, independently re-check the live repository state.

At minimum:

1. fetch current `main` HEAD;
2. inspect open pull requests and recent merges;
3. inspect the latest DeltaGrid CI, CodeQL and Live Public Boundary results;
4. distinguish public/founder boundary health from production deployment parity;
5. read `.ai/STATE.json` as a **snapshot**, not as current truth;
6. read the controlling current documentation listed below.

Never repeat an old SHA as current merely because it appears in this file.

## Product direction

DeltaGrid is being developed as a live, showable quantitative-research product while the underlying system keeps improving.

The sequence is:

**showable/usable project and public site -> improve continuously while live -> mature founder operating system -> production SaaS architecture when the product actually needs multi-user tenancy.**

The public visitor should be able to understand what an operator/admin can inspect without receiving the authority to perform private actions. Public views should therefore mirror safe parts of the founder information architecture using sanitized snapshots, deterministic examples or explicit unavailable states.

Do not expose founder records, protected evidence, credentials, private runtime state, write routes or execution authority in order to make the demo look more complete.

## Founder expectations for delivery

- Keep building without waiting for routine approval.
- Ask the founder only when an external account action, secret, legal/business choice or genuinely irreversible decision cannot be completed safely through connected tools.
- Prefer shipping small verified improvements over writing speculative roadmaps.
- Question implementation choices and look for contradictions before merging.
- Do not create cosmetic churn merely to show activity.
- Keep the frontend restrained, dense and human-designed; avoid generic AI-startup visual patterns, excessive cards, gradients, oversized copy and decorative filler.
- Keep public prose natural and maintainer-like rather than ceremonial or AI-sounding.
- Preserve the zero-spend constraint unless the founder explicitly changes it.

## Current controlling documents

Read these before deep work:

- `README.md` — living public overview and current research/trading status.
- `docs/README.md` — documentation map and status labels.
- `docs/DELIVERY_ROADMAP.json` — current delivery lanes and fixed delivery rules.
- `docs/RESEARCH_POLICY.md` — current research policy.
- `docs/RISK_POLICY.md` — current risk policy.
- `docs/SAFETY_INVARIANTS.md` — safety invariants.
- `docs/DELTAGRID_FINAL_FREEZE.md` — controlling completed-research freeze.
- `docs/M104_READINESS_LOCK.md` — prospective Mission 104 programme lock.
- `web/docs/PRODUCT_ARCHITECTURE.md` — current product/public-demo architecture.
- `web/docs/SECURITY_BOUNDARY.md` — public/founder/machine boundary.
- `web/docs/RESEARCH_ENGINE.md` — founder research engine.

Historical documents may be accurate about their own phase but must not override current policy or authority.

## Non-negotiable interpretation rules

### Research claims

Do not claim DeltaGrid has a validated profitable strategy unless new controlling evidence explicitly establishes one. At the snapshot represented here, it does not.

A passing software test is not alpha. A public demo is not alpha. A working execution component is not trading authorization.

### Authority

Keep these concepts separate:

- software capability;
- research permission;
- protected-stage permission;
- candidate observation;
- paper execution;
- live execution;
- exchange credentials;
- order authority;
- capital authority.

Do not infer a higher stage from implementation of a lower one.

### Production evidence

A green PR or push live-boundary check proves reachability/isolation on the tested boundary. It does **not** prove that production serves the latest `main` revision.

Production freshness needs separate exact-revision provenance, currently designed around `deltagrid-release.json` and the production-parity/release workflows.

A missing or stale production marker is a deployment/provenance defect. It is not evidence of founder-auth bypass, private-data exposure, trading-authority leakage or a security breach.

### Public versus founder

The public observer is read-only and sanitized. The founder gateway and research workspace are separate authenticated surfaces. Never solve a demo problem by weakening that separation.

## Repository map

```text
contracts/                 versioned machine/authority contracts
docs/                      current docs, historical records and evidence maps
offchain/                  research, custody, governance and projection code
offchain/tests/            deterministic Python verification suite
ops/founder-agent/         outbound-only local restricted executor
web/                       public observer + founder Worker + research engine
web/research-app/          founder React/Vite research workspace
web/docs/                   product/security/research web documentation
scripts/                   frozen/supported local verification/operator tooling
.github/workflows/         CI, CodeQL, release and live-boundary automation
.ai/                       model continuity snapshots and bootstrap instructions
```

## Public product model

The public product should show the *shape* of the real system:

- research state;
- evidence/provenance;
- market/dossier views that are safe to publish;
- mission/programme progression;
- risk and readiness state;
- system health;
- clear explanation of what remains closed.

Where founder-only data would be required, use sanitized/demo data and say so. Avoid fake live values or mock authority.

## Release discipline

Before merge:

- inspect the exact diff;
- run/observe the relevant focused tests;
- require DeltaGrid CI green;
- require CodeQL green when applicable;
- require Live Public Boundary green;
- do not merge around a safety/governance failure merely to get a green badge.

After merge:

- verify whether the production release actually ran;
- verify exact deployed SHA separately;
- recheck public/founder anonymous isolation;
- keep production provenance distinct from code correctness.

## Documentation policy

DeltaGrid maintains two documentation tracks.

### 1. Human/public documentation

Purpose: explain the product, architecture, research record, safety model and how the system is organised to a reviewer, engineer or potential user.

Style: concise, specific, technical when needed, natural prose. Do not write generic "AI product" copy or repeat slogans. Prefer concrete system behaviour and diagrams/tables where they improve understanding.

Primary surfaces: root `README.md`, `web/docs/`, and files classified as current public documentation.

### 2. AI/model continuity material

Purpose: let a future model quickly reconstruct where to look, what not to assume, what the current blockers were, and how to verify freshness.

Primary surfaces: `.ai/CONTINUITY.md` and `.ai/STATE.json`.

These files may include operational snapshot data, but no secrets. They must explicitly mark volatile fields and tell the next model to reverify them.

## When context is lost

A new model should not ask the founder to paste old chats first. Use the repository and connected GitHub evidence as the primary reconstruction path. Old chat summaries are useful context, not source-of-truth repository state.

Recommended bootstrap order:

1. `.ai/CONTINUITY.md`
2. `.ai/STATE.json`
3. current GitHub `main`, PRs and workflow runs
4. `README.md`
5. `docs/README.md`
6. `docs/DELIVERY_ROADMAP.json`
7. current policy/safety files relevant to the requested change
8. the exact code/tests being modified

If repository evidence contradicts this file, repository evidence wins unless a controlling contract/policy says otherwise.
