# Reviewing DeltaGrid publicly

The public DeltaGrid site is a static observer for the research system, not a trading console and not a copy of the founder workspace.

Live observer: https://deltagrid-observer.tushar142004.workers.dev

A useful review starts in three places:

1. Open the live observer to see the public research terminal, configured coverage, data-source contracts, sanitized workspace previews, and current authority boundaries.
2. Read [Architecture](ARCHITECTURE.md) and [Security boundary](SECURITY_BOUNDARY.md) to see how the public Worker is kept separate from the authenticated founder surface.
3. Read [Continuity](CONTINUITY.md) for the current release, monitoring, dependency, and operational posture rather than relying on an older project summary.

The public build is intentionally limited. It contains no founder-authored research records, protected evidence, broker or exchange credentials, private APIs, order path, paper/live trading state, or capital controls. Demo data is deterministic and sanitized; the interface must not imply profitability or live execution that the system has not established.

## What is worth inspecting

The strongest engineering claims in the hosted layer are testable rather than cosmetic:

- the observer is built as a static public surface;
- the founder gateway sits behind Cloudflare Access and also validates the Access JWT and exact founder identity itself;
- anonymous boundary checks probe the public observer and private founder routes on an hourly schedule and after merges to `main`;
- production releases require an exact current-`main` commit and publish a release marker that is checked against the deployed site;
- scheduled monitoring compares production with current `main` so a stale public deployment cannot remain silent;
- Cloudflare release credentials are scoped to the deployment steps that actually need them;
- founder D1 schema migration remains a separate, fail-closed operation rather than an implicit side effect of a Worker deploy.

Those controls are deliberately separate from research authority. A healthy deployment does not authorize a trial, open protected evidence, validate alpha, create an order, or deploy capital.

## What not to infer

DeltaGrid is visible because it is useful as an engineering and research-governance record. Public availability should not be read as a claim that the project has discovered a profitable strategy. It has not.

For the hosted product itself, the most current design rationale is in [Public design direction](PUBLIC_DESIGN.md), and deployment details are in [Public hosting](PUBLIC_HOSTING.md).
