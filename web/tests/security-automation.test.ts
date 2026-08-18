import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const codeql = fs.readFileSync("../.github/workflows/codeql.yml", "utf8");
const dependabot = fs.readFileSync("../.github/dependabot.yml", "utf8");

test("CodeQL scans application, research Python, and GitHub Actions surfaces", () => {
  assert.match(codeql, /javascript-typescript/u);
  assert.match(codeql, /- python/u);
  assert.match(codeql, /- actions/u);
  assert.match(codeql, /build-mode: none/u);
  assert.match(codeql, /queries: security-extended/u);
});

test("CodeQL keeps least privilege and immutable, internally consistent action pins", () => {
  assert.match(codeql, /permissions:\n  contents: read\n  security-events: write/u);
  assert.doesNotMatch(codeql, /pull_request_target/u);
  assert.doesNotMatch(codeql, /secrets\./u);

  const checkout = /actions\/checkout@([0-9a-f]{40})/u.exec(codeql);
  const init = /github\/codeql-action\/init@([0-9a-f]{40})/u.exec(codeql);
  const analyze = /github\/codeql-action\/analyze@([0-9a-f]{40})/u.exec(codeql);
  assert.ok(checkout, "CodeQL checkout must use a full immutable SHA");
  assert.ok(init, "CodeQL init must use a full immutable SHA");
  assert.ok(analyze, "CodeQL analyze must use a full immutable SHA");
  assert.equal((codeql.match(/actions\/checkout@/gu) ?? []).length, 1);
  assert.equal((codeql.match(/github\/codeql-action\/init@/gu) ?? []).length, 1);
  assert.equal((codeql.match(/github\/codeql-action\/analyze@/gu) ?? []).length, 1);
  assert.equal(init[1], analyze[1], "CodeQL init and analyze must use the same reviewed release commit");
});

test("CodeQL runs on review, main, manual dispatch, and a bounded weekly schedule", () => {
  assert.match(codeql, /pull_request:/u);
  assert.match(codeql, /push:/u);
  assert.match(codeql, /workflow_dispatch:/u);
  assert.match(codeql, /41 3 \* \* 3/u);
  assert.match(codeql, /timeout-minutes: 20/u);
  assert.match(codeql, /fail-fast: false/u);
});

test("Dependabot is conservative and does not mutate the research Python dependency graph", () => {
  assert.match(dependabot, /package-ecosystem: "github-actions"/u);
  assert.match(dependabot, /directory: "\/"/u);
  assert.match(dependabot, /package-ecosystem: "npm"/u);
  assert.match(dependabot, /directory: "\/web"/u);
  assert.equal((dependabot.match(/interval: "weekly"/gu) ?? []).length, 2);
  assert.equal((dependabot.match(/open-pull-requests-limit: 5/gu) ?? []).length, 2);
  assert.equal((dependabot.match(/rebase-strategy: "disabled"/gu) ?? []).length, 2);
  assert.match(dependabot, /update-types:\n\s+- "minor"\n\s+- "patch"/u);
  assert.doesNotMatch(dependabot, /package-ecosystem: "pip"/u);
  assert.doesNotMatch(dependabot, /offchain/u);
});
