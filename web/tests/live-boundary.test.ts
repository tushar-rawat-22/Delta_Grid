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

test("live verifier checks public availability and all anonymous private surfaces", () => {
  assert.match(verifier, /deltagrid-observer\.tushar142004\.workers\.dev/u);
  assert.match(verifier, /deltagrid-founder-gateway\.tushar142004\.workers\.dev/u);
  assert.match(verifier, /PUBLIC_RESEARCH_DEMO=PASS/u);
  assert.match(verifier, /PUBLIC_PRIVATE_MARKER_SCAN=PASS/u);

  for (const privatePath of [
    "/research",
    "/founder",
    "/api/research/v1/bootstrap",
    "/agent/v1/status",
  ]) {
    assert.ok(verifier.includes(`$FOUNDER_BASE${privatePath}`), privatePath);
  }

  assert.match(verifier, /verify_anonymous_denied/u);
  assert.ok(verifier.includes("cloudflareaccess\\.com"));
  assert.match(verifier, /401\|403/u);
  assert.match(verifier, /ANONYMOUS_PRIVATE_SURFACE_COUNT=4/u);
  assert.match(verifier, /DELTAGRID_LIVE_PUBLIC_PRIVATE_BOUNDARY=PASS/u);
});

test("anonymous machine-path check is non-mutating and detects missing edge isolation", () => {
  assert.match(verifier, /\$FOUNDER_BASE\/agent\/v1\/status/u);
  assert.doesNotMatch(verifier, /--request\s+POST|\s-X\s+POST/u);
  assert.doesNotMatch(verifier, /--data|--form/u);
});
