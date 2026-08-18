import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("M101 binding planner remains trusted-local and authority-zero", () => {
  const source = fs.readFileSync("scripts/plan-m101-binding.mjs", "utf8");
  const documentation = fs.readFileSync("docs/M101_BINDING_PLAN.md", "utf8");

  for (const marker of [
    "READ_ONLY_PREPARATION_ONLY",
    "commands_executed: false",
    "writes_performed: false",
    "permit_issued: false",
    "permit_consumed: false",
    "trial_reserved: false",
    "result_execution_authorized: false",
    'authority_effect: "NONE"',
  ]) assert.match(source, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&"), "u"));

  for (const forbidden of [
    "fetch(",
    "node:http",
    "node:https",
    "child_process",
    "execSync",
    "spawnSync",
    "writeFileSync",
    "appendFile",
    "createWriteStream",
    "wrangler",
    "sqlite",
  ]) assert.equal(source.includes(forbidden), false, forbidden);

  assert.match(documentation, /cannot execute any of those steps/u);
  assert.match(documentation, /trusted local operator boundary/u);
});
