import assert from "node:assert/strict";
import test from "node:test";

import { demoOperatorWorkflow, demoResearchGates } from "../lib/public-demo-data.ts";

test("public research gates expose statistical decision depth without inventing evidence", () => {
  const byStage = new Map(demoResearchGates.map((gate) => [gate.stage, gate]));

  assert.equal(byStage.get("Statistical programme")?.state, "NO RESULT");
  assert.equal(byStage.get("Statistical programme · estimand")?.state, "LOCKED DEMO");
  assert.equal(byStage.get("Statistical programme · uncertainty")?.state, "NO RESULT");
  assert.equal(byStage.get("Statistical programme · costs")?.state, "NO RESULT");
  assert.equal(byStage.get("Multiplicity review")?.state, "REQUIRED");
  assert.equal(byStage.get("Robustness review")?.state, "NO RESULT");
  assert.equal(byStage.get("Candidate decision")?.state, "NONE");
  assert.equal(byStage.get("Protected opening")?.state, "CLOSED");
  assert.match(byStage.get("Statistical programme")?.detail ?? "", /qualifying statistical result/u);
});

test("candidate workflow requires statistical evidence before promotion", () => {
  const candidateLane = demoOperatorWorkflow.find((item) => item.lane === "Candidate decision");

  assert.equal(candidateLane?.state, "NO RESULT");
  assert.match(candidateLane?.next ?? "", /estimand/u);
  assert.match(candidateLane?.next ?? "", /uncertainty/u);
  assert.match(candidateLane?.next ?? "", /costs/u);
  assert.match(candidateLane?.next ?? "", /multiplicity/u);
  assert.match(candidateLane?.next ?? "", /robustness/u);
});

test("statistical demo keeps candidate, execution and protected stages fail-closed", () => {
  const candidateGate = demoResearchGates.find((gate) => gate.stage === "Candidate decision");
  const executionGate = demoResearchGates.find((gate) => gate.stage === "Execution / accounting");
  const protectedGate = demoResearchGates.find((gate) => gate.stage === "Protected opening");

  assert.equal(candidateGate?.state, "NONE");
  assert.equal(executionGate?.state, "NOT AUTHORIZED");
  assert.equal(protectedGate?.state, "CLOSED");
});
