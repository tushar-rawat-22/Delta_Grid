import assert from "node:assert/strict";
import test from "node:test";

import { demoOperatorWorkflow, demoResearchGates } from "../lib/public-demo-data.ts";

test("public research gates expose statistical decision depth without inventing evidence", () => {
  const byStage = new Map(demoResearchGates.map((gate) => [gate.stage, gate]));

  assert.equal(byStage.get("Statistical programme")?.state, "NO RESULT");
  assert.equal(byStage.get("Multiplicity review")?.state, "REQUIRED");
  assert.equal(byStage.get("Robustness review")?.state, "NO RESULT");
  assert.equal(byStage.get("Candidate decision")?.state, "NONE");
  assert.equal(byStage.get("Protected opening")?.state, "CLOSED");
});

test("candidate workflow requires statistical evidence before promotion", () => {
  const candidateLane = demoOperatorWorkflow.find((item) => item.lane === "Candidate decision");

  assert.equal(candidateLane?.state, "NO RESULT");
  assert.match(candidateLane?.next ?? "", /multiplicity/u);
  assert.match(candidateLane?.next ?? "", /robustness/u);
  assert.match(candidateLane?.next ?? "", /qualifying evidence/u);
});

test("statistical demo text does not claim alpha, profitability or authorization", () => {
  const text = JSON.stringify({ demoResearchGates, demoOperatorWorkflow }).toLowerCase();

  for (const forbidden of [
    "validated profitable strategy",
    "selected candidate",
    "paper trading authorized",
    "live trading authorized",
    "protected opening authorized",
  ]) {
    assert.equal(text.includes(forbidden), false, forbidden);
  }
});
