import assert from "node:assert/strict";
import test from "node:test";

import {
  DEMO_NAV,
  PUBLIC_DEMO_IDENTITY,
  assertPublicDemoInvariants,
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

test("trial preview remains synthetic and cannot imply persistence or execution", () => {
  assert.ok(demoTrialLedger.some((entry) => entry.status === "SIMULATED"));
  assert.ok(demoTrialLedger.some((entry) => entry.status === "SANITIZED"));
  assert.ok(demoTrialLedger.some((entry) => entry.status === "UNAVAILABLE"));
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Execution binding")?.value, "None");
  assert.equal(demoTrialLedger.find((entry) => entry.field === "Accounting ledger")?.value, "No cash-flow records");
});