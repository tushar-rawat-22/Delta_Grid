import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflow = fs.readFileSync("../.github/workflows/public-observer-release.yml", "utf8");

test("public release remains exact-current-main and static-only preflighted", () => {
  assert.match(workflow, /release_sha:/u);
  assert.match(workflow, /\^\[0-9a-f\]\{40\}\$/u);
  assert.match(workflow, /git fetch --no-tags origin main/u);
  assert.match(workflow, /Refusing to deploy a commit that is not current main/u);
  assert.match(workflow, /npm run check/u);
  assert.match(workflow, /npm run verify:public-deploy/u);
  assert.match(workflow, /--config wrangler\.jsonc/u);
  assert.match(workflow, /--strict/u);
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
});

test("public release does not gain founder application or state credentials", () => {
  assert.match(workflow, /CLOUDFLARE_API_TOKEN: \$\{\{ secrets\.CLOUDFLARE_API_TOKEN \}\}/u);
  assert.match(workflow, /CLOUDFLARE_ACCOUNT_ID: \$\{\{ secrets\.CLOUDFLARE_ACCOUNT_ID \}\}/u);

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
