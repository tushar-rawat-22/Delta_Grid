# DeltaGrid Web and Research Engine

This directory is the web and Cloudflare edge component of the canonical DeltaGrid repository. It contains three isolated surfaces across two existing Workers:

- a public, static DeltaGrid product shell plus the existing read-only observer routes;
- an Access-protected, founder-only research workspace and research API; and
- the existing Access-protected founder control plane with its durable fixed-action command ledger.

The public product is intentionally inspectable. Anyone can open the site, understand the configured system, browse verified public state, see sanitized product views and follow the visible login link. The live founder workspace remains authenticated. The research workspace is `NON_RAB1_RESEARCH_ONLY`. None of these surfaces is trading or capital authority.

## Live system

- Public observer: `https://deltagrid-observer.tushar142004.workers.dev`
- Founder control plane: `https://deltagrid-founder-gateway.tushar142004.workers.dev/founder`
- Founder research workspace and login target: `https://deltagrid-founder-gateway.tushar142004.workers.dev/research`
- Research API: `/api/research/v1/*`, exact-founder Access JWT plus same-origin CSRF protection.
- Machine API: `/agent/v1/{claim,start,complete,evidence,status}`, protected by its own path-scoped Cloudflare Access Service Auth application and replay-protected HMAC requests.
- Durable state: Cloudflare D1, with command lifecycle, append-only receipts/events, nonce replay protection, Provider Registry, Instrument Master and temporal evidence envelopes.

The public site stays a nine-route Next.js static export with no database, authentication or command path. Its homepage is the public product shell and the remaining observer routes preserve the admitted projection. Public product previews use verified public facts or deterministic sanitized fixtures only. They never embed founder notes, D1-backed private state, provider secrets or protected RAB-1 evidence.

Anyone may reach the founder login flow. Cloudflare Access denies the protected workspace unless the request matches its Allow policy, and the founder Worker separately validates the Access JWT and exact founder identity before returning founder assets or API data. There is no public signup.

The separate research namespace stores founder work and independent public-provider observations; it has no reference to protected M100–M103 or RAB-1 custody.

## Admitted public state

- core commit: `d94441f2f32fd8edc7b416beecd88b2b087d01a9`
- projection SHA-256: `0e13dae7cddddff1110d79630682bfbc1495f1bc23d5ea95cf15e2906fb967c4`
- projection contract hash: `bf288d8b6349c2843b5196fa1857ae9c464773bbcf7cad9d821785ea67dfb6e8`

A verified snapshot is not automatically fresh. Replacing it remains an explicit admission and review action.

## Verification

```bash
npm run install:locked-safe
npm run check
```

`npm run check` verifies dependency and lifecycle-script policy, public/founder source boundaries, public deployment configuration, D1 schema and transition guards, TypeScript, lint, unit tests, static output privacy and a founder Worker dry-run.

See [`docs/RESEARCH_ENGINE.md`](docs/RESEARCH_ENGINE.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/SECURITY_BOUNDARY.md`](docs/SECURITY_BOUNDARY.md) and [`docs/PUBLIC_HOSTING.md`](docs/PUBLIC_HOSTING.md).

## Authority boundary

This web component cannot authorize Mission 104, protected research, model training, paper/live trading, exchange or broker credentials, orders, portfolio allocation or capital deployment.
