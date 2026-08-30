import assert from "node:assert/strict";
import test from "node:test";

import {
  assertPublicDemoInvariants,
  demoResearchGates,
} from "../lib/public-demo-data.ts";

test("public observer explains why research admission remains closed", () => {
  assert.doesNotThrow(() => assertPublicDemoInvariants());

  const repository = demoResearchGates.find((gate) => gate.stage === "Admission · repository");
  const dataset = demoResearchGates.find((gate) => gate.stage === "Admission · dataset / split");
  const budget = demoResearchGates.find((gate) => gate.stage === "Admission · budget / control");
  const decision = demoResearchGates.find((gate) => gate.stage === "Admission · decision");

  assert.equal(repository?.state, "UNAVAILABLE");
  assert.equal(dataset?.state, "SANITIZED");
  assert.equal(budget?.state, "DEMO");
  assert.equal(decision?.state, "CLOSED");
  assert.match(decision?.detail ?? "", /does not authorize execution or protected research/i);
});

test("admission preview does not claim protected data, persistence, permits, or execution", () => {
  const admissionText = demoResearchGates
    .filter((gate) => gate.stage.startsWith("Admission"))
    .map((gate) => `${gate.stage} ${gate.state} ${gate.detail}`)
    .join(" ");

  assert.match(admissionText, /protected, validation and holdout data remain unavailable and unopened/i);
  assert.match(admissionText, /without reserving a real trial or consuming a canonical budget/i);
  assert.match(admissionText, /No canonical admission decision, decision hash or permit exists here/i);
  assert.doesNotMatch(admissionText, /paper trading authorized|live trading authorized|capital authority granted/i);
});
