# Public hosting topology

DeltaGrid has two deliberately separate Cloudflare Workers surfaces.

## Public observer

`deltagrid-observer` is the public product surface. It is a nine-route Next.js static export served through Cloudflare Workers Static Assets from `web/out`.

The public Worker must remain static-assets-only. It has no Worker entrypoint, D1, KV, R2, Durable Object, queue, service binding, scheduled trigger, runtime environment variable, credential, founder command path, research write path, protected evidence path, or trading/capital authority.

The checked-in `web/wrangler.jsonc` is the deployment source of truth. `npm run verify:public-deploy` fails if a stateful or server-side runtime surface is added to that config without an explicit architectural change.

Current bootstrap endpoint:

- `https://deltagrid-observer.tushar142004.workers.dev`

For a business-facing production launch, move the observer to a Cloudflare Custom Domain. The `workers.dev` endpoint remains useful for bootstrap and diagnostics but is not the intended long-term branded origin.

## Founder gateway

`deltagrid-founder-gateway` is a separate Access-protected Worker. It owns the founder control plane, founder research workspace, research API, machine API, D1 binding and scheduled provider collection.

The founder gateway is not a fallback origin for the public observer. Public traffic must not gain access to founder routes, D1, secrets or authenticated research assets through routing convenience or shared bindings.

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

1. attach a branded Cloudflare Custom Domain to `deltagrid-observer`;
2. preserve the public/private Worker split;
3. add uptime and synthetic route checks from outside Cloudflare;
4. add deployment provenance to release records;
5. keep rollback to a known Worker version available;
6. enable only the minimum observability needed for each surface, with founder logs treated as sensitive operational data;
7. never add research execution, protected evidence, exchange credentials, order paths or capital authority to the public Worker.
