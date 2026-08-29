import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflow = fs.readFileSync("../.github/workflows/public-observer-rollback.yml", "utf8");

test("public rollback requires both an exact Worker version and release commit", () => {
  assert.match(workflow, /version_id:/u);
  assert.match(workflow, /release_sha:/u);
  assert.match(workflow, /\^\[0-9a-f\]\{8\}-\[0-9a-f\]\{4\}-\[0-9a-f\]\{4\}-\[0-9a-f\]\{4\}-\[0-9a-f\]\{12\}\$/u);
  assert.match(workflow, /\^\[0-9a-f\]\{40\}\$/u);
  assert.match(workflow, /ROLLBACK_PUBLIC_OBSERVER/u);
});

test("public rollback proves exact live release provenance before boundary verification", () => {
  const rollbackIndex = workflow.indexOf('wrangler rollback "$TARGET_VERSION_ID"');
  const provenanceIndex = workflow.indexOf("Verify exact live release provenance after rollback");
  const markerIndex = workflow.indexOf("/deltagrid-release.json?rollback_provenance=$TARGET_RELEASE_SHA");
  const matchIndex = workflow.indexOf('if [ "$observed" != "$expected" ]');
  const boundaryIndex = workflow.indexOf("verify-live-boundary.sh");

  assert.ok(rollbackIndex >= 0);
  assert.ok(provenanceIndex > rollbackIndex);
  assert.ok(markerIndex > provenanceIndex);
  assert.ok(matchIndex > markerIndex);
  assert.ok(boundaryIndex > matchIndex);
  assert.match(workflow, /ROLLBACK_PROVENANCE=PASS/u);
});

test("public rollback keeps Cloudflare credentials scoped to Cloudflare CLI steps", () => {
  const jobEnvStart = workflow.indexOf("    env:");
  const stepsStart = workflow.indexOf("    steps:");
  assert.ok(jobEnvStart >= 0 && stepsStart > jobEnvStart);
  const jobEnv = workflow.slice(jobEnvStart, stepsStart);
  assert.doesNotMatch(jobEnv, /CLOUDFLARE_API_TOKEN|CLOUDFLARE_ACCOUNT_ID/u);

  const tokenBindings = workflow.match(/CLOUDFLARE_API_TOKEN: \$\{\{ secrets\.CLOUDFLARE_API_TOKEN \}\}/gu) ?? [];
  const accountBindings = workflow.match(/CLOUDFLARE_ACCOUNT_ID: \$\{\{ secrets\.CLOUDFLARE_ACCOUNT_ID \}\}/gu) ?? [];
  assert.equal(tokenBindings.length, 4);
  assert.equal(accountBindings.length, 4);
});
