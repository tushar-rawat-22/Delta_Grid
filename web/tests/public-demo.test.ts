import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import {
  DEMO_NAV,
  PUBLIC_DEMO_IDENTITY,
  assertPublicDemoInvariants,
  demoDatasetCustody,
  demoHealth,
  demoHypotheses,
  demoMarketSeries,
  demoOperatorWorkflow,
  demoSystemBoundary,
  demoTrialLedger,
} from "../lib/public-demo-data.ts";

test("public research demo is deterministic, sanitized and non-authorizing", () => {
  assert.doesNotThrow(() => assertPublicDemoInvariants());
  assert.equal(PUBLIC_DEMO_IDENTITY.mode, "DEMO_MODE");
  assert.equal(PUBLIC_DEMO_IDENTITY.provenance, "DEMO_FIXTURE");
  assert.equal(PUBLIC_DEMO_IDENTITY.authority_effect, "NONE");
  assert.equal(DEMO_NAV.length, 11);
  assert.deepEqual(
    DEMO_NAV.map((item) => item.label),
    ["Cockpit", "Intelligence", "Hypotheses", "Research gates", "Trial ledger", "Markets", "Compare", "Macro", "Notebook", "Data health", "System boundary"],
  );
});

test("public demo fixtures contain no live-market or founder authority claim", () => {
  assert.ok(demoMarketSeries.length >= 7);
  assert.ok(demoHypotheses.every((item) => item.id.startsWith("DEMO-HYP-")));
  assert.ok(demoHealth.every((item) => item.rights === "DEMO_ONLY"));

  const fixtureText = JSON.stringify({ demoMarketSeries, demoHypotheses, demoHealth, demoDatasetCustody, demoTrialLedger }).toLowerCase();
  for (const forbidden of ["live price", "validated profitable", "selected candidate", "paper trading authorized", "live trading authorized"]) {
    assert.equal(fixtureText.includes(forbidden), false, forbidden);
  }
});

test("public trial ledger exposes workflow bindings without execution or accounting authority", () => {
  const byField = new Map(demoTrialLedger.map((item) => [item.field, item]));
  assert.equal(byField.get("Trial identity")?.status, "SIMULATED");
  assert.equal(byField.get("Dataset binding")?.status, "SANITIZED");
  assert.equal(byField.get("Execution binding")?.value, "None");
  assert.equal(byField.get("Execution binding")?.status, "NOT AUTHORIZED");
  assert.equal(byField.get("Accounting ledger")?.value, "No cash-flow records");
  assert.equal(byField.get("Accounting ledger")?.status, "UNAVAILABLE");
});

test("public dataset custody exposes the evidence model without private material", () => {
  const byBinding = new Map(demoDatasetCustody.map((item) => [item.binding, item]));
  assert.equal(byBinding.get("Dataset identity")?.state, "SANITIZED");
  assert.equal(byBinding.get("Content digest")?.state, "SIMULATED");
  assert.equal(byBinding.get("Chronology")?.state, "VERIFIED DEMO");
  assert.equal(byBinding.get("Source rights")?.value, "DEMO_ONLY");
  assert.equal(byBinding.get("Custody receipt")?.state, "UNAVAILABLE");
  assert.equal(JSON.stringify(demoDatasetCustody).includes("CLOUDFLARE"), false);
});

test("public operator workflow explains gates without granting authority", () => {
  const byLane = new Map(demoOperatorWorkflow.map((item) => [item.lane, item]));
  assert.equal(byLane.get("Research intake")?.state, "DEMO");
  assert.equal(byLane.get("Dataset custody")?.state, "SANITIZED");
  assert.equal(byLane.get("Trial execution")?.state, "NOT AUTHORIZED");
  assert.equal(byLane.get("Candidate decision")?.state, "NO RESULT");
  assert.equal(byLane.get("Protected stage")?.state, "CLOSED");
});

test("public system boundary stays fail-closed", () => {
  const byLayer = new Map(demoSystemBoundary.map((item) => [item.layer, item.state]));
  assert.equal(byLayer.get("Public observer"), "SANITIZED");
  assert.equal(byLayer.get("Founder gateway"), "ACCESS CONTROLLED");
  assert.equal(byLayer.get("Founder APIs"), "DENIED ANONYMOUSLY");
  assert.equal(byLayer.get("Release provenance"), "UNVERIFIED");
  assert.equal(byLayer.get("Research authority"), "NONE");
  assert.equal(byLayer.get("Public interactions"), "READ ONLY");
});

test("public demo component has no private network or write surface", () => {
  const source = fs.readFileSync("components/public-research-demo.tsx", "utf8");
  for (const forbidden of ["fetch(", "XMLHttpRequest", "WebSocket(", "/api/research/v1/", "csrf_token", "method: \"POST\"", "method: 'POST'"]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
  assert.match(source, /DEMO MODE/u);
  assert.match(source, /Log in for Founder Mode/u);
  assert.match(source, /Operator workflow/u);
  assert.match(source, /Trial ledger/u);
  assert.match(source, /NO EXECUTION OR ACCOUNTING SIDE EFFECTS/u);
  assert.match(source, /Dataset custody/u);
  assert.match(source, /NO PRIVATE CUSTODY MATERIAL/u);
  assert.match(source, /MERGED ≠ CI-GREEN ≠ DEPLOYED/u);
});
