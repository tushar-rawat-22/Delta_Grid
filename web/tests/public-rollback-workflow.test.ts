import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflow = fs.readFileSync("../.github/workflows/public-observer-rollback.yml", "utf8");

test("public rollback requires main, an exact version and explicit human confirmation", () => {
  assert.match(workflow, /test "\$GITHUB_REF" = "refs\/heads\/main"/u);
  assert.match(workflow, /version_id:/u);
  assert.match(workflow, /confirmation:/u);
  assert.match(workflow, /ROLLBACK_PUBLIC_OBSERVER/u);
  assert.match(workflow, /\^\[0-9a-f\]\{8\}-\[0-9a-f\]\{4\}-\[0-9a-f\]\{4\}-\[0-9a-f\]\{4\}-\[0-9a-f\]\{12\}\$/u);
  assert.match(workflow, /wrangler versions view "\$TARGET_VERSION_ID"/u);
});

test("public rollback pins its tooling to the immutable dispatched commit", () => {
  assert.match(workflow, /ref: \$\{\{ github\.sha \}\}/u);
  assert.match(workflow, /test "\$\(git rev-parse HEAD\)" = "\$GITHUB_SHA"/u);
  assert.doesNotMatch(workflow, /ref: main/u);
});

test("public rollback shares the production concurrency lock and verifies isolation afterward", () => {
  assert.match(workflow, /group: public-observer-production/u);
  const rollbackIndex = workflow.indexOf("wrangler rollback");
  const liveIndex = workflow.indexOf("verify-live-boundary.sh");
  const preIndex = workflow.indexOf("pre-rollback-deployment.txt");
  const postIndex = workflow.indexOf("post-rollback-deployment.txt");

  assert.ok(preIndex >= 0);
  assert.ok(rollbackIndex > preIndex);
  assert.ok(postIndex > rollbackIndex);
  assert.ok(liveIndex > postIndex);
  assert.match(workflow, /GITHUB_STEP_SUMMARY/u);
});

test("public rollback cannot acquire founder or research authority", () => {
  assert.match(workflow, /CLOUDFLARE_API_TOKEN: \$\{\{ secrets\.CLOUDFLARE_API_TOKEN \}\}/u);
  assert.match(workflow, /CLOUDFLARE_ACCOUNT_ID: \$\{\{ secrets\.CLOUDFLARE_ACCOUNT_ID \}\}/u);

  for (const forbidden of [
    "DELTAGRID_FOUNDER_EMAIL",
    "DELTAGRID_RESEARCH_CSRF_KEY",
    "DELTAGRID_AGENT_HMAC_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "FRED_API_KEY",
    "wrangler.founder.jsonc",
    "d1 migrations apply",
    "d1 execute",
    "issue-development-permit",
    "admit-development",
    "run-development",
  ]) {
    assert.doesNotMatch(workflow, new RegExp(forbidden.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")));
  }
});
