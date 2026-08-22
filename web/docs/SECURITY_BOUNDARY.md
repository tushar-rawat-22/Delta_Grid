# DeltaGrid Web Security Boundary

Compromise of the public observer must not provide a path to the founder Worker, local runtime or DeltaGrid authority. Compromise of one machine credential must not be enough to execute an action.

## Public observer

- static admitted projection only;
- no database, auth, API, Server Action, private runtime, provider credential, analytics or command path;
- output and source leak scans before deployment;
- static-output verification reads build artifacts directly rather than using check-then-open filesystem sequences, so CI does not rely on a separate existence check remaining true before inspection.

## Founder human boundary

- exact founder identity, independent MFA and a 30-minute application session;
- Worker independently validates JWT signature, issuer, audience, expiry and exact email;
- command creation is same-origin form only, exact typed confirmation, five-minute TTL and fixed action registry.

## Research boundary

- every `/research` HTML, JavaScript and CSS request runs through the Worker and revalidates the founder Access JWT;
- `/api/research/v1/*` is same-origin only; writes require a 15-minute HMAC CSRF proof bound to the Access subject;
- provider keys are Worker secrets and never enter browser responses, D1 rows, logs or static assets;
- provider requests use fixed HTTPS hosts, allowlisted functions/symbols, bounded bodies and strict schemas;
- provider failure, quota exhaustion and stale state remain explicit; the UI never manufactures a current value;
- research observations, records and receipts are isolated under `research_*`, `NON_RAB1_RESEARCH_ONLY`, authority effect `NONE`;
- no research query references M100–M103, RAB-1 or temporal evidence-envelope custody;
- editable founder records use optimistic revisions and append-only revision snapshots.

## Founder machine boundary

- separate `/agent/*` Service Auth application and token;
- exact service JWT audience plus HMAC over method, path, timestamp, nonce and body hash;
- durable nonce replay prevention;
- outbound-only local agent, Keychain credentials and mode-0600 config;
- reviewed local executor and provider-pilot source lives under `ops/founder-agent/`; runtime configuration, Keychain material, raw provider payloads and local receipts remain outside Git;
- exact core commit and clean worktree required;
- no remote parameters, shell, code, URL, path, environment or plugin;
- detailed output remains local; only status and SHA-256 hashes are returned.

## Production release automation

- GitHub release jobs expose Cloudflare production credentials only to the individual Wrangler steps that require Cloudflare API access;
- dependency installation, audits, compilation, tests, repository-boundary verification and anonymous live-boundary checks run without those credentials;
- public and founder deployment jobs run only when the workflow dispatch itself targets `refs/heads/main`, preventing accidental execution of a stale or feature-branch workflow definition;
- the requested deploy commit must independently equal current `main`; the dispatch-ref check and deploy-target check are separate invariants;
- GitHub environment branch/tag protection remains the external control that should prevent a deliberately modified non-main workflow from receiving production environment access, because a repository-local guard cannot protect against a branch that removes its own guard;
- public and founder deployment workflows use separate protected GitHub environments and separate concurrency locks;
- founder release preflight resolves the remote D1 database through the checked-in `DELTAGRID_SYSTEM_DB` binding rather than a duplicated database-name literal, so configuration identity remains the source of truth;
- founder application secrets are not imported into GitHub Actions; deployed Worker secret bindings remain at Cloudflare;
- schema migration remains a separate reviewed operation and is never performed implicitly by a Worker release.

## Authority

The fixed actions verify, capture already-approved public data, create backups, refresh local public projections or run approved tests. The research workspace may organize independent founder research, but it cannot authorize protected research, Mission 104, paper/live trading, credentials, orders, allocation or capital. Expected authority remains hard-coded to `NONE`.
