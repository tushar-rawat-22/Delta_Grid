import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflow = fs.readFileSync("../.github/workflows/live-public-boundary.yml", "utf8");
const verifier = fs.readFileSync("scripts/verify-live-boundary.sh", "utf8");

test("live public boundary monitor is scheduled and manually runnable", () => {
  assert.match(workflow, /workflow_dispatch:/u);
  assert.match(workflow, /schedule:/u);
  assert.match(workflow, /23 \* \* \* \*/u);
  assert.match(workflow, /permissions:\n\s+contents: read/u);
  assert.match(workflow, /bash web\/scripts\/verify-live-boundary\.sh/u);
});

test("live boundary workflow needs no deployment or founder credentials", () => {
  assert.doesNotMatch(workflow, /secrets\./u);
  assert.doesNotMatch(workflow, /CLOUDFLARE_API_TOKEN/u);
  assert.doesNotMatch(workflow, /wrangler\s+deploy/u);
  assert.doesNotMatch(verifier, /Authorization:/u);
  assert.doesNotMatch(verifier, /Cookie:/u);
  assert.doesNotMatch(verifier, /CF-Access-Client/u);
});

test("live verifier checks public availability and anonymous founder isolation", () => {
  assert.match(verifier, /deltagrid-observer\.tushar142004\.workers\.dev/u);
  assert.match(verifier, /deltagrid-founder-gateway\.tushar142004\.workers\.dev\/research/u);
  assert.match(verifier, /PUBLIC_RESEARCH_DEMO=PASS/u);
  assert.match(verifier, /PUBLIC_PRIVATE_MARKER_SCAN=PASS/u);
  assert.match(verifier, /FOUNDER_ACCESS_REDIRECT=PASS/u);
  assert.match(verifier, /FOUNDER_ACCESS_DENIED_ANONYMOUS=PASS/u);
  assert.match(verifier, /DELTAGRID_LIVE_PUBLIC_PRIVATE_BOUNDARY=PASS/u);
});
