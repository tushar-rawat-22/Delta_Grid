import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const action = fs.readFileSync(
  "research-app/src/preregistration-handoff-action.tsx",
  "utf8",
);
const workbench = fs.readFileSync(
  "research-app/src/preregistration-workbench.tsx",
  "utf8",
);
const model = fs.readFileSync(
  "research-app/src/preregistration-handoff-model.ts",
  "utf8",
);

test("founder review exposes handoff only after structural readiness", () => {
  assert.match(workbench, /PreregistrationHandoffAction/u);
  assert.match(workbench, /review\.structural_lock_ready/u);
  assert.match(action, /Generate handoff manifest/u);
  assert.match(action, /Download canonical handoff JSON/u);
  assert.match(action, /data:application\/json/u);
});

test("handoff action adds no server write or authority request", () => {
  for (const forbidden of [
    "fetch(",
    "apiWrite(",
    "csrf_token",
    'method: "POST"',
    'method: "PUT"',
    'method: "PATCH"',
    'method: "DELETE"',
    "/api/research/v1/records",
    "/api/research/v1/compare",
    "issue-development-permit",
    "admit-development",
    "run-development",
  ]) {
    assert.equal(action.includes(forbidden), false, forbidden);
  }

  assert.match(action, /trusted local/u);
  assert.match(action, /cannot issue a permit/u);
  assert.match(action, /cannot.*reserve a trial/su);
  assert.match(action, /cannot.*authorize research execution/su);
});

test("handoff model keeps all canonical owner resolution outside the browser", () => {
  assert.match(model, /LOCAL_OPERATOR_WORKFLOW_ONLY/u);
  assert.match(model, /browser_writable: false/u);
  assert.match(model, /canonical_state_write: false/u);
  assert.match(model, /permit_issue: false/u);
  assert.match(model, /permit_consume: false/u);
  assert.match(model, /trial_reserve: false/u);
  assert.match(model, /execution_spec_claim: false/u);
  assert.match(model, /result_execution: false/u);
  assert.match(model, /protected_stage_open: false/u);
  assert.match(model, /mission104_authorize: false/u);
  assert.match(model, /trading_authorize: false/u);
});
