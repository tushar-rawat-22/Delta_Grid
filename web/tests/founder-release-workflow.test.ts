import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflow = fs.readFileSync("../.github/workflows/founder-gateway-release.yml", "utf8");
const founderConfig = fs.readFileSync("wrangler.founder.jsonc", "utf8");

test("founder release requires a main-dispatched exact current-main commit", () => {
  assert.match(workflow, /release_sha:/u);
  assert.match(workflow, /\^\[0-9a-f\]\{40\}\$/u);
  assert.match(workflow, /if: github\.ref == 'refs\/heads\/main'/u);
  assert.match(workflow, /git fetch --no-tags origin main/u);
  assert.match(workflow, /git rev-parse FETCH_HEAD/u);
  assert.match(workflow, /Refusing to deploy a commit that is not current main/u);
  assert.match(workflow, /persist-credentials: false/u);
});

test("Cloudflare production credentials are unavailable to founder build and test steps", () => {
  const jobEnvStart = workflow.indexOf("    env:");
  const stepsStart = workflow.indexOf("    steps:");
  assert.ok(jobEnvStart >= 0 && stepsStart > jobEnvStart);
  const jobEnv = workflow.slice(jobEnvStart, stepsStart);
  assert.doesNotMatch(jobEnv, /CLOUDFLARE_API_TOKEN|CLOUDFLARE_ACCOUNT_ID/u);

  const tokenBindings = workflow.match(/CLOUDFLARE_API_TOKEN: \$\{\{ secrets\.CLOUDFLARE_API_TOKEN \}\}/gu) ?? [];
  const accountBindings = workflow.match(/CLOUDFLARE_ACCOUNT_ID: \$\{\{ secrets\.CLOUDFLARE_ACCOUNT_ID \}\}/gu) ?? [];
  assert.equal(tokenBindings.length, 3);
  assert.equal(accountBindings.length, 3);
});

test("founder release checks remote D1 migrations through the configured binding", () => {
  assert.match(founderConfig, /"binding": "DELTAGRID_SYSTEM_DB"/u);
  assert.match(founderConfig, /"database_name": "deltagrid-founder-system"/u);

  const commandStart = workflow.indexOf("wrangler d1 migrations list");
  const remoteFlag = workflow.indexOf("--remote", commandStart);
  assert.ok(commandStart >= 0 && remoteFlag > commandStart);
  const migrationCommand = workflow.slice(commandStart, remoteFlag);
  assert.match(migrationCommand, /DELTAGRID_SYSTEM_DB/u);
  assert.doesNotMatch(migrationCommand, /deltagrid-founder-system/u);

  assert.match(workflow, /No migrations to apply!/u);
  assert.doesNotMatch(workflow, /d1 migrations apply/u);
  assert.doesNotMatch(workflow, /d1 execute/u);
});

test("founder release deploys only after the full gate and checks anonymous isolation", () => {
  const checkIndex = workflow.indexOf("npm run check");
  const migrationIndex = workflow.indexOf("d1 migrations list");
  const deployIndex = workflow.indexOf("wrangler deploy");
  const liveIndex = workflow.indexOf("verify-live-boundary.sh");

  assert.ok(checkIndex >= 0);
  assert.ok(migrationIndex > checkIndex);
  assert.ok(deployIndex > migrationIndex);
  assert.ok(liveIndex > deployIndex);
  assert.match(workflow, /--config wrangler\.founder\.jsonc/u);
  assert.match(workflow, /--strict/u);
  assert.match(workflow, /versions list/u);
  assert.match(workflow, /--json/u);
});

test("founder release workflow does not import founder application secrets", () => {
  for (const forbidden of [
    "DELTAGRID_FOUNDER_EMAIL",
    "DELTAGRID_RESEARCH_CSRF_KEY",
    "DELTAGRID_AGENT_HMAC_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "FRED_API_KEY",
  ]) {
    assert.doesNotMatch(workflow, new RegExp(`${forbidden}:`));
  }
});
