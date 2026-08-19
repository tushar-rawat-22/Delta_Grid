import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const workflowPaths = [
  "../.github/workflows/deltagrid-ci.yml",
  "../.github/workflows/live-public-boundary.yml",
  "../.github/workflows/public-observer-release.yml",
  "../.github/workflows/public-observer-rollback.yml",
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

const REVIEWED_ACTIONS = ["actions/checkout", "actions/setup-python", "actions/setup-node"] as const;

test("company workflows use only reviewed actions with immutable full-SHA pins", () => {
  for (const action of REVIEWED_ACTIONS) {
    assert.ok(activeUses.some((line) => line.startsWith(`uses: ${action}@`)), `${action} must remain in the workflow set`);
  }

  for (const line of activeUses) {
    const match = /^uses: ([^@\s]+)@([0-9a-f]{40})$/u.exec(line);
    assert.ok(match, `active action must use an immutable 40-character SHA: ${line}`);
    assert.ok(REVIEWED_ACTIONS.includes(match[1] as (typeof REVIEWED_ACTIONS)[number]), `unreviewed action identity: ${match[1]}`);
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

test("every Node setup step explicitly disables package-manager caching", () => {
  assert.equal(packageJson.packageManager, undefined);
  const devEngines = packageJson.devEngines as Record<string, unknown> | undefined;
  assert.equal(devEngines?.packageManager, undefined);
  assert.doesNotMatch(joined, /^\s*cache:\s*/mu);
  assert.doesNotMatch(joined, /cache-dependency-path:/u);

  for (const [path, workflow] of workflows) {
    if (!workflow.includes("uses: actions/setup-node@")) continue;
    const setupBlocks = workflow.split(/(?=\n\s*- name: )/u).filter((block) => block.includes("uses: actions/setup-node@"));
    assert.ok(setupBlocks.length > 0, `${path} must expose its setup-node block`);
    for (const block of setupBlocks) {
      assert.match(block, /["']?package-manager-cache["']?: false/u, `${path} must explicitly disable setup-node package caching`);
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
