import assert from "node:assert/strict";
import test from "node:test";
import {
  currentProjection,
  P1_CORE_COMMIT,
  P1_PROJECTION_SHA256,
  projectionAuthority,
} from "../lib/current-projection.ts";
import { AUTHORITY_BOOLEAN_FIELDS } from "../lib/projection/constants.ts";

test("checked-in P1.3 snapshot is bound to the admitted core commit and digest", () => {
  assert.equal(currentProjection.manifest.repository_commit, P1_CORE_COMMIT);
  assert.equal(currentProjection.projection.core_identity.repository_commit, P1_CORE_COMMIT);
  assert.equal(currentProjection.projectionSha256, P1_PROJECTION_SHA256);
  assert.equal(currentProjection.manifest.projection_sha256, P1_PROJECTION_SHA256);
});

test("admitted projection cannot expose operational authority", () => {
  for (const field of AUTHORITY_BOOLEAN_FIELDS) {
    assert.equal(projectionAuthority[field], false, field);
  }
  assert.equal(projectionAuthority.maximum_verdict_authority_effect, "NONE");
  assert.equal(projectionAuthority.production_statistical_adapter_count, 0);
  assert.equal(projectionAuthority.production_protected_evaluator_count, 0);
});
