# DeltaGrid Research Cockpit v0

## Status and authority

This document explains the local interface authorized by
`contracts/DELTAGRID_RESEARCH_COCKPIT_UI_V1.json`. The contract is the exact
machine-readable Mission 96B authority. Mission 96A remains the authoritative
source of research-control-plane projections.

The cockpit is a single-user, loopback-only, read-only presentation. It does
not contain research, accounting, risk, validation, promotion, execution, or
trading logic. It cannot reserve or admit trials, append lifecycle events,
finalize results, write a ledger, query an exchange, or deploy capital.

Passing software verification does not establish a profitable strategy.

## Operating modes

The cockpit supports exactly two modes:

- **DEMO** loads one of two committed, canonical, hash-verified synthetic
  Mission 96A snapshots. Demo startup creates no ledger and performs no fixture
  loading or trial execution. The healthy scenario shows a verified synthetic
  non-alpha control. The degraded scenario adds a deterministic
  `COMPLETED_WITHOUT_RESULT_LINK` demonstration incident.
- **CONNECTED** opens an existing ledger through Mission 96A's
  `ReadOnlyTrialLedger`, constructs `ResearchControlPlaneService`, and requests
  a fresh snapshot at an explicit UTC observation timestamp. The cockpit does
  not query SQLite or result artifacts directly.

The interface labels demo evidence as synthetic and non-alpha. A degraded demo
is explicitly identified as a demonstration incident, not a current system
failure.

## Start a local demonstration

From the repository root, launch the healthy demonstration with:

```bash
/Users/tusharrawat/deltagrid/offchain/.venv/bin/python -m offchain.research.cockpit --mode demo --demo-scenario healthy
```

Launch the degraded demonstration with:

```bash
/Users/tusharrawat/deltagrid/offchain/.venv/bin/python -m offchain.research.cockpit --mode demo --demo-scenario degraded
```

The process prints one bootstrap URL after the HTTP server is listening. Open
that URL on the same machine. The URL is a one-time credential: the first
successful request consumes it, sets a process-local `HttpOnly`,
`SameSite=Strict` session cookie, and redirects to the cockpit. Reusing the
bootstrap URL is rejected. Stopping the process invalidates the session.

Use `--open-browser` only when the standard-library `webbrowser` module should
open the printed local URL automatically. No browser is opened before the
server is listening.

## Connected observation

Connected mode requires all four Mission 96A resource identities:

```bash
/Users/tusharrawat/deltagrid/offchain/.venv/bin/python -m offchain.research.cockpit \
  --mode connected \
  --ledger /absolute/path/to/existing-trials.sqlite3 \
  --result-root /absolute/path/to/existing-results \
  --repository-root /absolute/path/to/Delta_Grid \
  --expected-repository-commit 0123456789abcdef0123456789abcdef01234567
```

The expected commit must be exactly 40 lowercase hexadecimal characters.
Connected paths are not returned by the metadata endpoint. Mission 96A exposes
only hash-derived path identities in the snapshot.

## Local containment

The host is not configurable. The server binds exactly to `127.0.0.1` and
accepts only `127.0.0.1:<selected-port>` or
`localhost:<selected-port>` Host headers. It does not trust forwarded headers,
implement proxy awareness, emit CORS headers, serve directories, or translate
arbitrary filesystem paths.

Only these resources exist:

- one-time `GET /session/<token>`;
- authenticated `GET` and `HEAD` for `/`, `/assets/app.css`,
  `/assets/app.js`, `/api/v1/meta`, and `/api/v1/snapshot`.

Write-oriented HTTP methods return `405 Method Not Allowed`. There is no write
endpoint.

Every HTML, CSS, JavaScript, and JSON response disables caching and carries a
restrictive Content Security Policy plus `nosniff`, frame denial, no-referrer,
same-origin opener, and same-origin resource headers. Static assets are local;
there are no external fonts, analytics, telemetry, CDNs, or external API
requests.

## Exact presentation

Before a snapshot crosses the browser boundary, the cockpit recursively turns
every Python integer into its exact base-10 string. Booleans remain booleans,
null remains null, strings remain strings, and floats are rejected. Browser
code does not convert or calculate authoritative metric values. It provides
only text, lifecycle-status, and verification-status filtering while retaining
Mission 96A trial, result, and incident order.

The browser keeps the current snapshot only in memory. It uses no local
storage, session storage, IndexedDB, Cache API, service worker, source map,
remote asset, or persistent session.

## Permanent boundary

The cockpit grants no strategy research, development-market evaluation,
validation access, holdout access, protected-data access, model training,
model promotion, signal generation, portfolio construction, exchange access,
credential access, paper trading, live trading, capital deployment, autonomous
research, autonomous promotion, or autonomous execution.

The demonstration artifacts retain `SYNTHETIC_ONLY_NON_ALPHA_CONTROL` and
`NO_PROFITABILITY_INFERENCE`. They are interface evidence, not alpha evidence
and not permission to resume research.
