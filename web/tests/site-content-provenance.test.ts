import assert from "node:assert/strict";
import test from "node:test";
import { statusItems } from "../lib/site-content.ts";

function status(label: string) {
  const item = statusItems.find((entry) => entry.label === label);
  assert.ok(item, `missing status item: ${label}`);
  return item;
}

test("P1.3 keeps non-projected research claims document-derived", () => {
  assert.equal(status("Validated alpha").provenance, "PUBLIC_DOCUMENT_DERIVED");
  assert.equal(status("Selected candidate").provenance, "PUBLIC_DOCUMENT_DERIVED");
});

test("P1.3 renders projected authority closures only from verified package", () => {
  for (const label of ["Mission 104", "Paper trading", "Live trading", "Capital authority"]) {
    assert.equal(status(label).provenance, "VERIFIED_P1_PROJECTION", label);
  }
  assert.equal(status("Mission 104").value, "NOT AUTHORIZED");
  assert.equal(status("Paper trading").value, "NOT AUTHORIZED");
  assert.equal(status("Live trading").value, "NOT AUTHORIZED");
  assert.equal(status("Capital authority").value, "NONE");
});
