import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflowPaths = [
  "../.github/workflows/deltagrid-ci.yml",
  "../.github/workflows/live-public-boundary.yml",
  "../.github/workflows/public-observer-release.yml",
  "../.github/workflows/founder-gateway-release.yml",
] as const;

const workflows = workflowPaths.map((path) => [path, fs.readFileSync(path, "utf8")] as const);
const joined = workflows.map(([, text]) => text).join("\n");
const activeUses = joined
  .split("\n")
  .map((line) => line.trim())
  .filter((line) => line.startsWith("uses:"));
const packageJson = JSON.parse(fs.readFileSync("package.json", "utf8")) as Record<string, unknown>;
const dependabot = fs.readFileSync("../.github/dependabot.yml", "utf8");

const CHECKOUT_V7_0_1 = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1";
const SETUP_PYTHON_V7_0_0 = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97";
const SETUP_NODE_V6_5_0 = "actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38";

test("company workflows use reviewed immutable action pins", () => {
  assert.ok(activeUses.includes(`uses: ${CHECKOUT_V7_0_1}`));
  assert.ok(activeUses.includes(`uses: ${SETUP_PYTHON_V7_0_0}`));
  assert.ok(activeUses.includes(`uses: ${SETUP_NODE_V6_5_0}`));

  for (const line of activeUses) {
    if (!line.includes("actions/checkout@") && !line.includes("actions/setup-python@") && !line.includes("actions/setup-node@")) continue;
    assert.match(line, /@[0-9a-f]{40}$/u);
  }
});

test("old action identities may exist only as historical comments, never active uses", () => {
  for (const oldPin of [
    "11bd71901bbe5b1630ceea73d27597364c9af683",
    "a26af69be951a213d495a4c3e4e4022e16d87065",
    "49933ea5288caeca8642d1e84afbd3f7d6820020",
  ]) {
    assert.ok(activeUses.every((line) => !line.includes(oldPin)), `old action pin became active: ${oldPin}`);
  }
});

test("Node setup does not silently enable package-manager caching", () => {
  assert.equal(packageJson.packageManager, undefined);
  const devEngines = packageJson.devEngines as Record<string, unknown> | undefined;
  assert.equal(devEngines?.packageManager, undefined);
  assert.doesNotMatch(joined, /^\s*cache:\s*/mu);
  assert.doesNotMatch(joined, /cache-dependency-path:/u);

  for (const [, workflow] of workflows) {
    if (!workflow.includes(SETUP_NODE_V6_5_0)) continue;
    if (workflow.includes("package-manager-cache:")) {
      assert.match(workflow, /package-manager-cache: false/u);
    }
  }
});

test("workflows retain least-privilege checkout credentials", () => {
  for (const [path, workflow] of workflows) {
    if (!workflow.includes("actions/checkout@")) continue;
    assert.match(workflow, /permissions:\n\s+contents: read/u, `${path} must keep contents read-only`);
    assert.match(workflow, /persist-credentials: false/u, `${path} must disable persisted Git credentials`);
  }
});

test("Dependabot never opens unattended major-version upgrade PRs", () => {
  const majorIgnore = /ignore:\n\s+- dependency-name: "\*"\n\s+update-types:\n\s+- "version-update:semver-major"/gu;
  const matches = dependabot.match(majorIgnore) ?? [];
  assert.equal(matches.length, 2, "github-actions and web npm must both ignore major updates");
  assert.match(dependabot, /actions-minor-patch:[\s\S]*?update-types:\n\s+- "minor"\n\s+- "patch"/u);
  assert.match(dependabot, /web-minor-patch:[\s\S]*?update-types:\n\s+- "minor"\n\s+- "patch"/u);
});
