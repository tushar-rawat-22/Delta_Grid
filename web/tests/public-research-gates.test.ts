import assert from "node:assert/strict";
import test from "node:test";

import {
  DEMO_NAV,
  PUBLIC_DEMO_IDENTITY,
  assertPublicDemoInvariants,
  demoOperatorWorkflow,
  demoResearchGates,
  demoTrialLedger,
} from "../lib/public-demo-data.ts";

test("public research demo exposes the founder research gate hierarchy without authority", () => {
  assert.doesNotThrow(() => assertPublicDemoInvariants());
  assert.equal(PUBLIC_DEMO_IDENTITY.authority_effect, "NONE");
  assert.ok(DEMO_NAV.some((item) => item.id === "gates" && item.label === "Research gates"));

  const execution = demoResearchGates.find((gate) => gate.stage === "Execution / accounting");
  const statistics = demoResearchGates.find((gate) => gate.stage === "Statistical programme");
  const protectedCandidate = demoResearchGates.find((gate) => gate.stage === "Protected opening · candidate");
  const protectedEvidence = demoResearchGates.find((gate) => gate.stage === "Protected opening · evidence");
  const protectedAuthorization = demoResearchGates.find((gate) => gate.stage === "Protected opening · authorization");
  const protectedOpening = demoResearchGates.find((gate) => gate.stage === "Protected opening");

  assert.equal(execution?.state, "NOT AUTHORIZED");
  assert.equal(statistics?.state, "NO RESULT");
  assert.equal(protectedCandidate?.state, "NONE");
  assert.equal(protectedEvidence?.state, "UNAVAILABLE");
  assert.equal(protectedAuthorization?.state, "ABSENT");
  assert.equal(protectedOpening?.state, "CLOSED");
});

test("research engine preview requires a verified result bundle without inventing an outcome", () => {
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Result bundle verification")?.state, "UNAVAILABLE");
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Deterministic engine application")?.state, "SIMULATED");
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Engine decision output")?.state, "NO RESULT");
  assert.equal(demoOperatorWorkflow.find((item) => item.lane === "Research engine")?.gate, "Verified result bundle");
  assert.equal(demoOperatorWorkflow.find((item) => item.lane === "Research engine")?.state, "NO RESULT");
});

test("statistical review exposes required decision structure without fabricating evidence", () => {
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Statistical programme · estimand")?.state, "LOCKED DEMO");
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Statistical programme · uncertainty")?.state, "NO RESULT");
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Statistical programme · costs")?.state, "NO RESULT");
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Multiplicity review")?.state, "REQUIRED");
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Robustness review")?.state, "NO RESULT");
  assert.equal(demoResearchGates.find((gate) => gate.stage === "Candidate decision")?.state, "NONE");
  assert.match(demoOperatorWorkflow.find((item) => item.lane === "Candidate decision")?.next ?? "", /estimand, uncertainty, costs, multiplicity and robustness/);
});

test("trial preview remains synthetic and cannot imply persistence or execution", () => {
  assert.ok(demoTrialLedger.some((entry) => entry.status === "SIMULATED"));
  assert.ok(demoTrialLedger.some((entry) => entry.status === "SANITIZED"));
  assert.ok(demoTrialLedger.some((entry) => entry.status === "UNAVAILABLE"));
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Execution binding")?.value, "None");
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Accounting ledger")?.value, "No cash-flow records");
});

test("trial preview exposes reproducibility requirements without claiming a canonical replay", () => {
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Code binding")?.status, "SANITIZED");
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Configuration binding")?.status, "LOCKED DEMO");
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Environment fingerprint")?.status, "UNAVAILABLE");
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Replay artifact")?.value, "No canonical replay artifact");
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Replay artifact")?.status, "UNAVAILABLE");
});
