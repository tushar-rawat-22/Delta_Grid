import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflow = fs.readFileSync("../.github/workflows/live-public-boundary.yml", "utf8");
const releaseWorkflow = fs.readFileSync("../.github/workflows/public-observer-release.yml", "utf8");
const verifier = fs.readFileSync("scripts/verify-live-boundary.sh", "utf8");

test("live public boundary monitor is scheduled and manually runnable", () => {
  assert.match(workflow, /workflow_dispatch:/u);
  assert.match(workflow, /schedule:/u);
  assert.match(workflow, /23 \* \* \* \*/u);
  assert.match(workflow, /permissions:\n\s+contents: read/u);
  assert.match(workflow, /bash web\/scripts\/verify-live-boundary\.sh/u);
});

test("live boundary concurrency keeps different trigger classes independent", () => {
  assert.match(
    workflow,
    /group: live-public-boundary-\$\{\{ github\.event_name \}\}-\$\{\{ github\.event\.pull_request\.number \|\| github\.ref \}\}/u,
  );
  assert.match(workflow, /cancel-in-progress: true/u);
  assert.doesNotMatch(
    workflow,
    /group: live-public-boundary-\$\{\{ github\.event\.pull_request\.number \|\| github\.ref \}\}/u,
  );
});

test("scheduled and manual production parity fail closed on missing or stale release identity", () => {
  assert.match(
    workflow,
    /if: github\.event_name == 'schedule' \|\| github\.event_name == 'workflow_dispatch'/u,
  );
  assert.match(workflow, /name: verify-production-parity/u);
  assert.match(workflow, /ref: main/u);
  assert.match(workflow, /deltagrid-release\.json\?production_parity=\$expected_sha/u);
  assert.match(workflow, /--write-out '%\{http_code\}'/u);
  assert.match(workflow, /Cache-Control: no-cache/u);
  assert.match(workflow, /FAIL: \$message/u);
  assert.match(workflow, /PUBLIC_PRODUCTION_PARITY=UNVERIFIED/u);
  assert.match(workflow, /PUBLIC_PRODUCTION_PARITY=DRIFT/u);
  assert.match(workflow, /PUBLIC_PRODUCTION_PARITY=PASS/u);
  assert.doesNotMatch(workflow, /PARITY_TRIGGER:/u);
  assert.doesNotMatch(workflow, /::warning title=DeltaGrid production parity unavailable/u);
  assert.doesNotMatch(workflow, /::warning title=DeltaGrid production drift/u);
});

test("manual release binds and still hard-fails unless the exact deployed SHA is live", () => {
  assert.match(
    releaseWorkflow,
    /node scripts\/bind-public-release-provenance\.mjs "\$RELEASE_SHA"/u,
  );
  assert.ok(
    releaseWorkflow.includes(
      `test "$(cat out/deltagrid-release.json)" = "{\\"release_sha\\":\\"$RELEASE_SHA\\"}"`,
    ),
  );
  assert.match(releaseWorkflow, /Prove exact release is live/u);
  assert.match(releaseWorkflow, /FAIL: deployed public observer does not report requested release SHA/u);
  assert.match(releaseWorkflow, /PUBLIC_RELEASE_IDENTITY=PASS/u);
});

test("live boundary workflow needs no deployment or founder credentials", () => {
  assert.doesNotMatch(workflow, /secrets\./u);
  assert.doesNotMatch(workflow, /CLOUDFLARE_API_TOKEN/u);
  assert.doesNotMatch(workflow, /wrangler\s+deploy/u);
  assert.doesNotMatch(verifier, /Authorization:/u);
  assert.doesNotMatch(verifier, /Cookie:/u);
  assert.doesNotMatch(verifier, /CF-Access-Client/u);
  assert.doesNotMatch(verifier, /--data|--form/u);
});

test("live monitor configures the private Worker as a base, not one privileged path", () => {
  assert.match(
    workflow,
    /DELTAGRID_FOUNDER_BASE: https:\/\/deltagrid-founder-gateway\.tushar142004\.workers\.dev/u,
  );
  assert.doesNotMatch(workflow, /DELTAGRID_FOUNDER_URL:/u);
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
    "/founder/actions",
    "/api/research/v1/records",
  ]) {
    assert.ok(verifier.includes(`$FOUNDER_BASE${privatePath}`), privatePath);
  }

  assert.match(verifier, /verify_anonymous_denied/u);
  assert.ok(verifier.includes("cloudflareaccess\\.com"));
  assert.match(verifier, /401\|403/u);
  assert.match(verifier, /ANONYMOUS_PRIVATE_SURFACE_COUNT=6/u);
  assert.match(verifier, /ANONYMOUS_MUTATION_SURFACE_COUNT=2/u);
  assert.match(verifier, /DELTAGRID_LIVE_PUBLIC_PRIVATE_BOUNDARY=PASS/u);
});

test("public homepage verification follows stable authority semantics, not old marketing copy", () => {
  for (const marker of ["Mission 104", "NOT AUTHORIZED", "Founder"]) {
    assert.ok(verifier.includes(`\"${marker}\"`), marker);
  }

  assert.doesNotMatch(verifier, /A public view of a private research system\./u);
  assert.doesNotMatch(verifier, /Explore Demo Mode/u);
  assert.match(verifier, /grep -Fqi/u);
});

test("anonymous mutation probes are bodyless and target founder-auth-gated write surfaces", () => {
  assert.match(verifier, /local method="\$\{4:-GET\}"/u);
  assert.match(verifier, /--request "\$method"/u);
  assert.match(
    verifier,
    /\$FOUNDER_BASE\/founder\/actions" \\\n  "founder_action_mutation" \\\n  "POST"/u,
  );
  assert.match(
    verifier,
    /\$FOUNDER_BASE\/api\/research\/v1\/records" \\\n  "founder_research_mutation" \\\n  "POST"/u,
  );
  assert.match(verifier, /No credentials, CSRF token, or payload are sent/u);
});

test("anonymous machine-path check remains non-mutating", () => {
  assert.match(
    verifier,
    /\$FOUNDER_BASE\/agent\/v1\/status" \\\n  "machine_api"\n/u,
  );
});
