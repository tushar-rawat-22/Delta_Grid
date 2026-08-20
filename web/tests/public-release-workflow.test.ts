import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflow = fs.readFileSync("../.github/workflows/public-observer-release.yml", "utf8");

test("public release remains exact-current-main and static-only preflighted", () => {
  assert.match(workflow, /release_sha:/u);
  assert.match(workflow, /\^\[0-9a-f\]\{40\}\$/u);
  assert.match(workflow, /if: github\.ref == 'refs\/heads\/main'/u);
  assert.match(workflow, /git fetch --no-tags origin main/u);
  assert.match(workflow, /Refusing to deploy a commit that is not current main/u);
  assert.match(workflow, /npm run check/u);
  assert.match(workflow, /npm run verify:public-deploy/u);
  assert.match(workflow, /--config wrangler\.jsonc/u);
  assert.match(workflow, /--strict/u);
});

test("Cloudflare production credentials are unavailable to public build and test steps", () => {
  const jobEnvStart = workflow.indexOf("    env:");
  const stepsStart = workflow.indexOf("    steps:");
  assert.ok(jobEnvStart >= 0 && stepsStart > jobEnvStart);
  const jobEnv = workflow.slice(jobEnvStart, stepsStart);
  assert.doesNotMatch(jobEnv, /CLOUDFLARE_API_TOKEN|CLOUDFLARE_ACCOUNT_ID/u);

  const tokenBindings = workflow.match(/CLOUDFLARE_API_TOKEN: \$\{\{ secrets\.CLOUDFLARE_API_TOKEN \}\}/gu) ?? [];
  const accountBindings = workflow.match(/CLOUDFLARE_ACCOUNT_ID: \$\{\{ secrets\.CLOUDFLARE_ACCOUNT_ID \}\}/gu) ?? [];
  assert.equal(tokenBindings.length, 2);
  assert.equal(accountBindings.length, 2);
});

test("public release proves the deployed observer is the requested commit before boundary checks", () => {
  const markerIndex = workflow.indexOf("Bind public build to requested release");
  const deployIndex = workflow.indexOf("wrangler deploy");
  const identityIndex = workflow.indexOf("Prove exact release is live");
  const liveIndex = workflow.indexOf("verify-live-boundary.sh");

  assert.ok(markerIndex >= 0);
  assert.ok(deployIndex > markerIndex);
  assert.ok(identityIndex > deployIndex);
  assert.ok(liveIndex > identityIndex);
  assert.match(workflow, /out\/deltagrid-release\.json/u);
  assert.match(workflow, /deltagrid-release\.json/u);
  assert.match(workflow, /PUBLIC_RELEASE_IDENTITY=PASS/u);
  assert.match(workflow, /deployed public observer does not report requested release SHA/u);
});

test("public release records version provenance and checks the live isolation boundary", () => {
  const deployIndex = workflow.indexOf("wrangler deploy");
  const statusIndex = workflow.indexOf("deployments status");
  const versionsIndex = workflow.indexOf("versions list");
  const liveIndex = workflow.indexOf("verify-live-boundary.sh");

  assert.ok(deployIndex >= 0);
  assert.ok(statusIndex > deployIndex);
  assert.ok(versionsIndex > deployIndex);
  assert.ok(liveIndex > versionsIndex);
  assert.match(workflow, /--json/u);
  assert.match(workflow, /GITHUB_STEP_SUMMARY/u);
  assert.match(workflow, /Requested commit/u);
  assert.match(workflow, /Live release identity/u);
});

test("public release does not gain founder application or state credentials", () => {
  for (const forbidden of [
    "DELTAGRID_FOUNDER_EMAIL",
    "DELTAGRID_RESEARCH_CSRF_KEY",
    "DELTAGRID_AGENT_HMAC_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "FRED_API_KEY",
    "d1 migrations apply",
    "d1 execute",
  ]) {
    assert.doesNotMatch(workflow, new RegExp(forbidden.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")));
  }
});
