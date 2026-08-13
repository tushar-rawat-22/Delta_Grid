import assert from "node:assert/strict";
import test from "node:test";
import { assertProductionProvenance } from "../lib/projection/provenance.ts";

test("production rejects demo fixture provenance", () => {
  assert.throws(
    () => assertProductionProvenance("DEMO_FIXTURE", "production"),
    /DEMO_FIXTURE_FORBIDDEN_IN_PRODUCTION/u,
  );
  assert.doesNotThrow(() => assertProductionProvenance("PUBLIC_DOCUMENT_DERIVED", "production"));
  assert.doesNotThrow(() => assertProductionProvenance("DEMO_FIXTURE", "development"));
});
