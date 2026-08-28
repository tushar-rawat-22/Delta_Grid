# DeltaGrid product and architecture

DeltaGrid is a quantitative research system built around one idea: a trading hypothesis should not become more trustworthy just because a backtest looks good.

The system separates research, evidence, review, operational readiness and authority. It keeps failed hypotheses in the record, binds important results to reproducible inputs, and makes higher-risk stages explicit instead of allowing one component to silently promote its own output.

The public site is a product demo and review surface. It is meant to show how the system thinks and how the operator workspace is organised without giving a visitor the ability to write private research, issue founder commands, access credentials or activate trading.

## What a visitor can see

The public observer is intentionally closer to an operator console than a marketing page. It exposes sanitized views of the same categories an operator cares about:

- current research state and programme progression;
- market and evidence views that are safe to publish;
- research/demo analysis with deterministic fixtures where private or live state would be inappropriate;
- risk and authority status;
- system and mission history;
- documentation and review material.

The goal is to let someone understand what DeltaGrid is capable of reviewing without turning the public site into an execution surface.

A public visitor can inspect the model of the system. They cannot become an operator by using the demo.

## What stays private

The founder side is a separate boundary. It contains the authenticated research workspace, private research records, founder-only API routes and the control-plane surfaces used for restricted operations.

Private surfaces are not embedded in the public bundle. Anonymous requests are checked independently at the edge and must not receive founder content.

The local founder agent is outbound-only. It does not open an inbound control port on the founder machine. Machine requests require the expected Access service identity plus a signed, replay-protected request before a supported command can be accepted.

## Current architecture

```text
                         public internet
                               |
                  +------------+------------+
                  |                         |
          Public observer             Founder gateway
          static/read-only             Cloudflare Access
                  |                         |
        sanitized product views        authenticated Worker
                  |                         |
        no private bindings        +--------+---------+
                                   |                  |
                              research UI       founder APIs
                                   |                  |
                                   +--------+---------+
                                            |
                                     D1/private state
                                            |
                                   outbound founder agent

        ------------------------------------------------------
                       repository / off-chain core
        ------------------------------------------------------
        contracts -> custody -> admission -> deterministic run
              -> independent verification -> governance
              -> read-only projection -> readiness inspection
```

### Public observer

The public observer is built from `web/` as a static asset surface. The production configuration deliberately carries no stateful binding. Public pages can show sanitized snapshots and deterministic demos, but they do not receive founder D1 access or command authority.

### Founder gateway and research workspace

The founder Worker is a different deployment with authenticated routes and private bindings. The research workspace can maintain founder-scoped research records and produce structured research material, but its current boundary remains non-RAB-1 research only. Being able to write a research note is not the same thing as being allowed to run protected research or trade.

### Off-chain research core

The Python core under `offchain/` owns the heavier research and governance machinery: data custody, admission, deterministic execution, result verification, statistical governance, public projection and operational-readiness inspection.

Important boundaries are represented in code and contracts rather than left as operator convention. The repository deliberately distinguishes implementation capability from authorization.

### Release and monitoring

GitHub Actions provides the software gate and deployment orchestration. CI, CodeQL and the live public/private-boundary check are separate signals. Production release provenance is checked separately so a reachable website is not automatically treated as proof that production serves the latest `main` commit.

The public deployment is designed for Cloudflare Workers. A release is expected to publish an immutable commit marker and then verify that exact marker from the live observer before the release is considered proven.

## Demo versus admin

The product direction is not to build two unrelated interfaces.

The public demo should mirror the *information architecture* of the founder workspace where that is safe: dossiers, evidence, programme state, risk, system health and review flows. Values that are private, mutable, credential-bearing or authority-bearing are replaced with sanitized snapshots, deterministic examples or explicit unavailable states.

That gives a reviewer a realistic picture of DeltaGrid without creating public write paths.

The founder workspace keeps the real authenticated controls. Public demo affordances that resemble an admin action must remain non-mutating and clearly marked as demonstration/review state.

## What DeltaGrid can do today

The repository contains a substantial research operating system rather than one strategy script. It includes causal and revision-aware data handling, deterministic trial execution, cost-aware accounting, sealed progression, statistical governance, independent verification, public projection, a founder research workspace, live boundary monitoring and a read-only operational readiness verdict.

It does **not** currently have a validated profitable strategy or a selected trading candidate. Paper trading, live trading, exchange credentials, orders and capital deployment remain outside the current authority boundary.

That distinction is intentional. Software completeness and research success are different questions.

## Product path

The near-term product path is deliberately practical:

1. **Showable live project** — a polished public observer that demonstrates the operator model safely.
2. **Usable founder system** — one coherent private workspace for research, evidence, readiness and controlled operations.
3. **Continuous improvement while live** — releases stay incremental and observable instead of waiting for a fictional final build.
4. **Production SaaS architecture later** — multi-user tenancy, billing, support, stronger deployment environments and user-specific authority are separate product work. They should not be faked into the current single-founder system.

The public demo can evolve toward that future without exposing private state or pretending that current research has earned trading authority.

## Technology map

| Area | Current implementation |
|---|---|
| Public product | Next.js static output under `web/` |
| Founder research UI | React/Vite workspace under `web/research-app/` |
| Public/founder edge | Cloudflare Workers |
| Founder state | Cloudflare D1 binding on the private Worker |
| Research/governance core | Python under `offchain/` |
| Local restricted executor | outbound-only founder agent under `ops/founder-agent/` |
| CI/security | GitHub Actions + CodeQL + repository policy tests |
| Release verification | exact-SHA release marker + live boundary checks |

## Where to read next

- [`../../README.md`](../../README.md) — project overview and current research/trading boundary.
- [`PUBLIC_REVIEW.md`](PUBLIC_REVIEW.md) — fast technical review of the hosted product.
- [`RESEARCH_ENGINE.md`](RESEARCH_ENGINE.md) — founder research-engine behaviour and data semantics.
- [`SECURITY_BOUNDARY.md`](SECURITY_BOUNDARY.md) — public, founder-human and founder-machine separation.
- [`../../docs/README.md`](../../docs/README.md) — documentation map and document-status rules.
- [`../../docs/DELIVERY_ROADMAP.json`](../../docs/DELIVERY_ROADMAP.json) — machine-readable delivery lanes and fixed rules.

For portfolio review, start with this file and the live observer. For research claims, use the research evidence and final project report rather than product copy.
