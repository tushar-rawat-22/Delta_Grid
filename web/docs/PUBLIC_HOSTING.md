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

## Production hardening sequence

After the first public release:

1. make every major product capability observable through a sanitized public view or public explanation;
2. keep the visible founder login connected to the existing Access-protected gateway;
3. preserve the two-Worker authority split and do not create a second hosting stack;
4. add uptime and synthetic route checks from outside Cloudflare;
5. add deployment provenance to release records;
6. keep rollback to a known Worker version available;
7. enable only the minimum observability needed for each surface, with founder logs treated as sensitive operational data;
8. never add research execution, protected evidence, exchange credentials, order paths or capital authority to the public Worker.
