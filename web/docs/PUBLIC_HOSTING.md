# Public hosting topology

DeltaGrid uses two existing Cloudflare Workers surfaces with one product-facing rule: the product is publicly observable, while private data and control remain authenticated.

## Public product shell

`deltagrid-observer` is the public product surface. It is a nine-route Next.js static export served through Cloudflare Workers Static Assets from `web/out`.

Anyone may open the site, navigate the public routes, inspect the project status and evidence model, see the configured research scope, review sanitized product views, and use the visible founder login entry point. Public views may use verified projection fields, public repository facts, and deterministic sanitized fixtures only.

The public Worker must remain static-assets-only. It has no Worker entrypoint, D1, KV, R2, Durable Object, queue, service binding, scheduled trigger, runtime environment variable, credential, founder command path, research write path, protected evidence path, or trading/capital authority.

The checked-in `web/wrangler.jsonc` is the deployment source of truth. `npm run verify:public-deploy` fails if a stateful or server-side runtime surface is added to that config without an explicit architectural change.

Current public endpoint:

- `https://deltagrid-observer.tushar142004.workers.dev`

A branded Cloudflare Custom Domain can replace the bootstrap `workers.dev` address later without changing the public/private authority model.

## Founder login and authenticated mode

The public site exposes a visible login link to the existing `deltagrid-founder-gateway`. That gateway is reachable on the Internet but remains protected by the existing Cloudflare Access application before founder assets, APIs, D1-backed state or control surfaces are returned.

Unauthenticated visitors may reach the Access login flow. They must not receive founder data merely because the login endpoint itself is public. Only the exact allowed founder identity may pass the Access policy, and the Worker independently verifies the Access JWT and founder identity again.

After successful founder authentication, the gateway may expose the real research workspace, founder control plane, research API, machine API, D1-backed records and scheduled-provider state within their existing authority boundaries.

The intended product model is therefore:

```text
public visitor
  -> public DeltaGrid shell / sanitized views
  -> visible Log in
  -> Cloudflare Access
  -> exact founder identity
  -> real founder workspace and private state
```

The public shell must never fetch private founder APIs, embed private values into static assets, or treat a public demo action as a real write. A public preview may reproduce the shape of a founder view only with deterministic sanitized fixtures.

## Release model

Public releases are exact-commit releases.

Before deployment:

1. the requested SHA must be a full 40-character commit;
2. the SHA must equal current `main`;
3. the repository must be clean;
4. locked dependencies are installed;
5. the complete web/founder gate passes;
6. the static public deployment boundary is re-verified.

The manual local command is:

```bash
cd web
npm run deploy:public
```

The repository also contains `.github/workflows/public-observer-release.yml` for controlled production releases. It requires `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` as GitHub secrets and an exact `release_sha` input. The Cloudflare token should be scoped only to the account and permissions needed to deploy this Worker.

### Public Observer rollback

`.github/workflows/public-observer-rollback.yml` is the manual emergency rollback path for the static public Worker. It accepts only an exact Cloudflare Worker version UUID and requires the separate confirmation phrase `ROLLBACK_PUBLIC_OBSERVER`. Release and rollback share the same `public-observer-production` concurrency group so they cannot mutate the Worker concurrently.

The workflow may run only from `main` and checks out the exact `github.sha` captured when the workflow was dispatched. That keeps the reviewed Wrangler tooling, lockfile, deployment boundary checks and live verifier bound to one immutable repository identity even if `main` advances while the rollback is running. Before changing production it confirms the requested version exists in Cloudflare and reasserts that the repository still describes a static-only public Worker. Production Cloudflare credentials are injected only into the four Wrangler steps that query or mutate Cloudflare; dependency installation, repository verification, and anonymous live-boundary checks do not receive them. The workflow records the active deployment before the change, invokes `wrangler rollback` with the exact version ID and a non-interactive audit message, records the resulting deployment/version state, and then requires the anonymous public/private boundary check to pass.

This is intentionally limited to `deltagrid-observer`. The Founder Gateway is not given a symmetric generic rollback workflow because it carries D1-backed state: rolling older application code over a newer durable schema can be incompatible even when Cloudflare can technically reactivate the Worker version. Founder rollback therefore remains a separately reviewed recovery decision rather than a one-input convenience action.

A Worker rollback reactivates a previously uploaded artifact; it does not rebuild an old Git commit and does not revert external resources. A successful Cloudflare command is therefore not by itself proof of recovery—the live boundary test remains mandatory afterward.

### Founder Gateway release

`.github/workflows/founder-gateway-release.yml` is the corresponding exact-commit release path for the authenticated Worker. It is manual-only, requires the requested SHA to equal current `main`, installs the locked dependency graph, runs the complete web/founder gate and refuses to deploy if the remote D1 database has unapplied checked-in migrations.

D1 migration application is deliberately not part of the Worker deployment workflow. A schema change is a separate production mutation that must be reviewed and applied independently before code depending on it is released. This prevents a routine code deployment from silently changing durable data structures.

The release workflow needs only the Cloudflare deployment API token and account ID. Founder application secrets are not copied into GitHub Actions: Wrangler validates that the required secret bindings already exist on the deployed Worker and preserves secrets not supplied by the release configuration.

After deployment the workflow records Cloudflare deployment/version state and runs the anonymous live-boundary verifier. A Founder Gateway release is therefore not considered complete merely because `wrangler deploy` returned success; anonymous isolation must still pass after the write.

## Unattended live-boundary verification

`.github/workflows/live-public-boundary.yml` provides an independent external smoke check from GitHub-hosted infrastructure. It runs hourly and may also be dispatched manually. The workflow needs no Cloudflare token, founder credential, cookie, Access service token, D1 binding, or deployment permission.

Its verifier, `web/scripts/verify-live-boundary.sh`, checks the live system from an anonymous Internet client. It requires the public homepage, sanitized Research Demo, expected security headers and public robots policy to remain available. It also fails if known founder-only markers appear in public HTML, or if the anonymous founder workspace stops being denied or redirected to Cloudflare Access.

This monitor is intentionally a boundary detector, not an authenticated Founder Mode test. It must never obtain credentials just to make the check more comprehensive: the security property being tested is that an anonymous observer cannot receive founder content.

A branded domain can later replace the two default endpoint variables without changing the verification model. Until then, the `workers.dev` hostname remains subject to the existing hostname-specific `X-Robots-Tag: noindex, nofollow` requirement.

## Production hardening sequence

After the first public release:

1. make every major product capability observable through a sanitized public view or public explanation;
2. keep the visible founder login connected to the existing Access-protected gateway;
3. preserve the two-Worker authority split and do not create a second hosting stack;
4. keep the external live-boundary workflow green and treat a failure as a release/security incident until explained;
5. use exact-commit GitHub release workflows so deployments can proceed without a developer laptop while remaining reviewable;
6. keep schema migrations separate from Worker deploys and fail closed on pending migrations;
7. keep the guarded public rollback path available, while requiring separate schema-aware review for any Founder Gateway rollback;
8. enable only the minimum observability needed for each surface, with founder logs treated as sensitive operational data;
9. never add research execution, protected evidence, exchange credentials, order paths or capital authority to the public Worker.
