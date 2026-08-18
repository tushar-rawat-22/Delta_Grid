import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("package exposes the trusted-local M101 binding planner", () => {
  const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
  assert.equal(pkg.scripts["plan:m101-binding"], "node scripts/plan-m101-binding.mjs");
});
