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

const CHECKOUT_V7_0_1 = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1";
const SETUP_PYTHON_V7_0_0 = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97";
const SETUP_NODE_V6_5_0 = "actions/setup-node@249970729cb0ef3589644e2896645e5dc5ba9c38";

test("company workflows use reviewed immutable action pins", () => {
  assert.ok(joined.includes(CHECKOUT_V7_0_1));
  assert.ok(joined.includes(SETUP_PYTHON_V7_0_0));
  assert.ok(joined.includes(SETUP_NODE_V6_5_0));

  assert.doesNotMatch(joined, /actions\/checkout@(?![0-9a-f]{40}\b)[^\s]+/u);
  assert.doesNotMatch(joined, /actions\/setup-python@(?![0-9a-f]{40}\b)[^\s]+/u);
  assert.doesNotMatch(joined, /actions\/setup-node@(?![0-9a-f]{40}\b)[^\s]+/u);
});

test("old GitHub Action runtime pins cannot silently return", () => {
  for (const oldPin of [
    "11bd71901bbe5b1630ceea73d27597364c9af683",
    "a26af69be951a213d495a4c3e4e4022e16d87065",
    "49933ea5288caeca8642d1e84afbd3f7d6820020",
  ]) {
    assert.ok(!joined.includes(oldPin), `old action pin returned: ${oldPin}`);
  }
});

test("Node setup cannot silently enable package-manager caching", () => {
  const nodeUses = joined.split(SETUP_NODE_V6_5_0).length - 1;
  const explicitNoCache = joined.split("package-manager-cache: false").length - 1;

  assert.ok(nodeUses > 0);
  assert.equal(explicitNoCache, nodeUses);
});

test("workflows retain least-privilege checkout credentials", () => {
  for (const [path, workflow] of workflows) {
    if (!workflow.includes("actions/checkout@")) continue;
    assert.match(workflow, /permissions:\n\s+contents: read/u, `${path} must keep contents read-only`);
    assert.match(workflow, /persist-credentials: false/u, `${path} must disable persisted Git credentials`);
  }
});
