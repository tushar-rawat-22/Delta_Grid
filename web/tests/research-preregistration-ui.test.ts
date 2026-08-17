import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync("research-app/src/preregistration-workbench.tsx", "utf8");
const main = fs.readFileSync("research-app/src/main.tsx", "utf8");

test("founder app mounts the preregistration review workbench", () => {
  assert.match(main, /PreregistrationWorkbench/u);
  assert.match(main, /preregistration-workbench\.css/u);
  assert.match(source, /compilePreregistrationReview/u);
  assert.match(source, /Preregistration review/u);
  assert.match(source, /READY FOR CANONICAL BINDING/u);
  assert.match(source, /BLOCKED/u);
});

test("preregistration review reads founder bootstrap but creates no write path", () => {
  assert.match(source, /\/api\/research\/v1\/bootstrap/u);
  assert.match(source, /credentials: "same-origin"/u);
  assert.match(source, /NON_RAB1_RESEARCH_ONLY/u);
  assert.match(source, /authority_effect !== "NONE"/u);

  for (const forbidden of [
    "apiWrite(",
    "csrf_token",
    'method: "POST"',
    'method: "PUT"',
    'method: "PATCH"',
    'method: "DELETE"',
    "/api/research/v1/records",
    "/api/research/v1/compare",
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});

test("canonical bindings are displayed as unresolved browser-nonwritable controls", () => {
  assert.match(source, /Canonical bindings/u);
  assert.match(source, /UNRESOLVED/u);
  assert.match(source, /browser writable/u);
  assert.match(source, /no persistence/u);
  assert.match(source, /no trial reservation/u);
  assert.match(source, /no execution authorization/u);
  assert.match(source, /This review creates no authority/u);
  assert.match(source, /authorize Mission 104/u);
  assert.match(source, /place an order/u);
  assert.match(source, /allocate capital/u);
});
