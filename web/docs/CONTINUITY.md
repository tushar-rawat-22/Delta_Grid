# DeltaGrid Web and Platform Continuity

This file is the short operational handoff for the hosted DeltaGrid platform. It is living documentation for maintainers and future continuation sessions. It does not replace the controlling research contracts, the final freeze, or the Mission 100–103 governance documents.

## Resume here

Before changing anything, independently verify the repository instead of trusting a copied chat checkpoint:

```bash
git fetch origin main
git rev-parse origin/main
git status --short
```

For GitHub-side work, inspect current `main`, open pull requests, and the latest exact-head CI/CodeQL/live-boundary runs before deciding whether an existing branch is still admissible. Do not merge a stale dependency or infrastructure branch merely because an older head was green.

## Hosted product boundary

DeltaGrid currently uses two separate Cloudflare Worker surfaces:

- `deltagrid-observer` is the public project/product surface. It is a static Next.js export with no D1, private API, credential, command, research-write, protected-evidence, trading, or capital path.
- `deltagrid-founder-gateway` is the authenticated private surface. Cloudflare Access is the outer gate; the Worker independently validates the Access JWT and exact founder identity before serving founder assets or APIs.

The public site intentionally explains the system and exposes sanitized Demo Mode. There is no public signup. Anonymous access to the real research workspace, founder control plane, research API, and machine API must remain denied or redirected to Cloudflare Access.

The external live-boundary workflow verifies the public homepage and sanitized research demo and anonymously probes the private `/research`, `/founder`, `/api/research/v1/bootstrap`, and `/agent/v1/status` surfaces. It runs for pull requests, every hour, manual dispatches, and every push to `main`, so the exact merged commit gets an immediate post-merge public/private boundary check instead of waiting for the next scheduled probe. A failure is a release/security incident until explained.

Scheduled and manual live-boundary runs also compare the public observer's cache-busted `deltagrid-release.json` marker with the repository's current `main`. This is deliberately not enforced on pull requests or pushes: public releases are manual, so a short source-versus-production gap after a merge is expected. Persistent drift at the next scheduled probe is an operational signal that the public release is stale or the release marker cannot be trusted.

## Release, dependency, and security-reporting posture

Production releases are manual, exact-current-`main` releases. Public and founder deployment workflows:

- must be dispatched from `main`;
- independently require the requested release SHA to equal current `main`;
- use immutable reviewed GitHub Action SHAs;
- install the locked web dependency graph through the reviewed lifecycle-script gate;
- run the complete release checks before deployment;
- expose Cloudflare credentials only to Wrangler steps that require Cloudflare API access;
- record deployment/version provenance and run the anonymous live-boundary verifier after deployment.

The public observer release additionally writes the exact requested commit into a static `deltagrid-release.json` asset immediately before deployment. After Wrangler returns, the workflow polls a cache-busted URL for that marker with an explicit no-cache request until the live observer reports the requested SHA, and only then runs the public/private boundary verifier. This avoids treating a stale cached marker as deployment proof while still distinguishing "deployment command succeeded" from "the exact reviewed build is actually serving" without adding application state, credentials, or research authority.

The Founder Gateway additionally fails closed if reviewed D1 migrations remain unapplied. Schema migration is a separate operation and is never performed implicitly by a Worker release.

The public observer has a guarded exact-version rollback workflow because it is stateless/static. There is intentionally no generic Founder Gateway rollback: Cloudflare Worker rollback does not roll D1 state backward, so founder recovery must remain schema-aware.

Dependabot is limited to reviewed minor/patch lines. Major dependency or GitHub Action changes are compatibility work, not unattended maintenance. Lifecycle-script-capable packages remain independently pinned by the package allowlist, the locked installer, and dependency verification.

The historical `offchain/requirements.txt` declaration remains frozen because Mission-era regression tests use it as part of the recorded research baseline. GitHub Actions installs the separate exact-pinned `offchain/ci-requirements.txt` graph instead. `offchain/tests/test_requirements_lock.py` rejects range pins in that CI lock, requires every frozen exact runtime pin to remain present at the historical version, and, on GitHub Actions, compares the installed `pip freeze` graph with the lock. CI-only test tooling can therefore receive explicit reviewed maintenance without silently changing the frozen research runtime, rewriting the historical mission dependency declaration, or allowing resolver drift during unrelated pull requests.

`SECURITY.md` is the public vulnerability-reporting entry point. Reports should be handled privately, without encouraging destructive testing, founder-data access, or testing against exchanges, brokers, credentials, or capital. A confirmed report follows the normal branch, test, CI, review, and guarded-release path rather than bypassing it as an emergency shortcut.

## Founder research and M101 bridge

The founder Research Engine stores independent `NON_RAB1_RESEARCH_ONLY` records and public-provider observations. Browser-side preregistration review and handoff generation have authority effect `NONE`.

A trusted-local V2 handoff verifier independently rehashes the handoff and embedded scientific review. The deterministic M101 binding planner can then derive the declared development intent and the required Mission 101/94/102/103 preparation order without executing commands or writing canonical state.

The planner is deliberately not an authority service. It cannot create a dataset descriptor, initialize the private authority runtime, issue or consume a permit, register a budget, reserve/admit a trial, execute a result, open protected evidence, authorize Mission 104, trade, or deploy capital.

The current safe ordering encoded by the planner is:

1. read the controlling Mission 101 contract and confirm result-bearing authority remains closed;
2. independently certify the existing forward-custody release read-only;
3. inspect the stable Mission 102 registry/family/variant identity read-only;
4. inspect the private Mission 101 authority runtime read-only;
5. create the exact `REAL_MARKET_DEVELOPMENT` descriptor only after those read-only prerequisites are proven;
6. initialize the private authority runtime only if inspection established that it is absent and the explicit acknowledgement is supplied;
7. issue one finite Mission 101 development permit against the exact repository/dataset/release/family identity;
8. register the finite Mission 94 development budget required for admission;
9. reserve one metadata-only Mission 101 admission, establishing the exact M94 reservation/request and M101 permit-consumption chain;
10. prepare and freeze the exact pre-result Mission 103 program using the now-existing M94/M101 bindings and stable M102 identities; and
11. separately founder-activate that exact frozen program, then stop before result-bearing Mission 102 execution unless a separate founder-authorized workflow explicitly reaches that boundary.

GitHub must never invent the private release, descriptor, permit, budget, reservation, runtime, or protected-evidence facts. Those remain trusted-local facts.

## Authority boundary that must survive every change

Public hosting, CI, monitoring, dependency maintenance, documentation, and deterministic planning do not grant research or trading authority.

Do not use GitHub automation to:

- create or consume Mission 101 permits;
- register or consume finite trial capacity;
- reserve/admit a development trial;
- run result-bearing Mission 102 research;
- freeze or activate a real Mission 103 program using invented private identities;
- open replication, validation, holdout, or other protected evidence;
- authorize Mission 104;
- introduce exchange/broker credentials, orders, paper/live trading, leverage, portfolio allocation, or capital deployment.

If a next step needs private local state or an irreversible founder decision, stop at a verified preparation boundary rather than guessing.

## Fast continuation checklist

A future continuation should be able to get on the same page in one pass:

1. read this file, `web/docs/SECURITY_BOUNDARY.md`, `web/docs/PUBLIC_HOSTING.md`, and `web/docs/M101_BINDING_PLAN.md`;
2. inspect current `main` and recent commits rather than trusting any embedded SHA in old chat text;
3. inspect every open PR and exact-head workflow runs;
4. merge only fully green work with an expected-head guard;
5. choose one bounded GitHub-only task at a time;
6. keep public/private isolation and authority effect `NONE` intact;
7. document any new architectural invariant here when it materially changes how the next session should resume.
