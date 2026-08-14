# DeltaGrid Web Security Boundary

Compromise of the public observer must not provide a path to the founder Worker, local runtime or DeltaGrid authority. Compromise of one machine credential must not be enough to execute an action.

## Public observer

- static admitted projection only;
- no database, auth, API, Server Action, private runtime, provider credential, analytics or command path;
- output and source leak scans before deployment.

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

## Authority

The fixed actions verify, capture already-approved public data, create backups, refresh local public projections or run approved tests. The research workspace may organize independent founder research, but it cannot authorize protected research, Mission 104, paper/live trading, credentials, orders, allocation or capital. Expected authority remains hard-coded to `NONE`.
