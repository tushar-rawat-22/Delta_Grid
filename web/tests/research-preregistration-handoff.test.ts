import assert from "node:assert/strict";
import test from "node:test";

import {
  compilePreregistrationReview,
  PREREGISTRATION_HEADINGS,
} from "../research-app/src/preregistration-model.ts";
import {
  compilePreregistrationHandoffManifest,
  PREREGISTRATION_HANDOFF_SCHEMA,
} from "../research-app/src/preregistration-handoff-model.ts";

function completeBody(): string {
  return PREREGISTRATION_HEADINGS.map(
    (heading, index) => `${heading}\nFounder declaration ${index + 1}.`,
  ).join("\n\n");
}

test("structurally complete review compiles to deterministic authority-zero handoff", async () => {
  const review = await compilePreregistrationReview({
    record_id: "55555555-5555-4555-8555-555555555555",
    revision: 3,
    title: "Cross-asset causal mechanism",
    body: completeBody(),
  });

  const first = await compilePreregistrationHandoffManifest(review);
  const second = await compilePreregistrationHandoffManifest(review);

  assert.equal(first.schema_version, PREREGISTRATION_HANDOFF_SCHEMA);
  assert.equal(first.handoff_status, "READY_FOR_TRUSTED_LOCAL_RESOLUTION");
  assert.equal(first.authority_effect, "NONE");
  assert.equal(first.boundary, "NON_RAB1_RESEARCH_ONLY");
  assert.equal(first.source_review.canonical_review_json, review.canonical_review_json);
  assert.equal(first.canonical_handoff_hash_sha256, second.canonical_handoff_hash_sha256);
  assert.equal(first.handoff_id, second.handoff_id);
  assert.match(first.canonical_handoff_hash_sha256, /^[0-9a-f]{64}$/u);
  assert.equal(first.canonical_resolution_requirements.length, 5);
  assert.deepEqual(
    first.canonical_resolution_requirements.map((requirement) => requirement.owner),
    [
      "M101_DATASET_DESCRIPTOR",
      "M101_DEVELOPMENT_PERMIT",
      "M94_TRIAL_LEDGER_VIA_M101",
      "M102_SEALED_EXPERIMENT_REGISTRY",
      "M103_PROGRAM_PROTOCOL",
    ],
  );
  assert.ok(
    first.canonical_resolution_requirements.every(
      (requirement) =>
        requirement.status === "UNRESOLVED" &&
        requirement.browser_writable === false &&
        requirement.trusted_resolution_boundary === "LOCAL_OPERATOR_WORKFLOW_ONLY",
    ),
  );
  assert.ok(Object.values(first.browser_effects).every((value) => value === false));
});

test("blocked scientific review cannot produce a handoff manifest", async () => {
  const body = PREREGISTRATION_HEADINGS.map(
    (heading, index) => `${heading}\n${index === 0 ? "[Founder: complete observation]" : `Founder declaration ${index + 1}.`}`,
  ).join("\n\n");
  const review = await compilePreregistrationReview({
    record_id: "66666666-6666-4666-8666-666666666666",
    revision: 1,
    title: "Blocked mechanism",
    body,
  });

  await assert.rejects(
    compilePreregistrationHandoffManifest(review),
    /PREREGISTRATION_HANDOFF_STRUCTURAL_REVIEW_BLOCKED/u,
  );
});

test("handoff manifest cannot inherit resolved or browser-writable canonical binding", async () => {
  const review = await compilePreregistrationReview({
    record_id: "77777777-7777-4777-8777-777777777777",
    revision: 2,
    title: "Binding safety",
    body: completeBody(),
  });
  const unsafe = structuredClone(review);
  unsafe.canonical_bindings.development_dataset = {
    ...unsafe.canonical_bindings.development_dataset,
    browser_writable: true as false,
  };

  await assert.rejects(
    compilePreregistrationHandoffManifest(unsafe),
    /PREREGISTRATION_HANDOFF_REVIEW_SOURCE_MISMATCH|PREREGISTRATION_HANDOFF_CANONICAL_BINDING_INVALID/u,
  );
});

test("handoff manifest cannot inherit a side effect", async () => {
  const review = await compilePreregistrationReview({
    record_id: "88888888-8888-4888-8888-888888888888",
    revision: 1,
    title: "Side-effect safety",
    body: completeBody(),
  });
  const unsafe = structuredClone(review);
  unsafe.side_effects.trial_reserved = true as false;

  await assert.rejects(
    compilePreregistrationHandoffManifest(unsafe),
    /PREREGISTRATION_HANDOFF_REVIEW_SOURCE_MISMATCH|PREREGISTRATION_HANDOFF_SIDE_EFFECT_INVALID/u,
  );
});

test("V2 producer independently rehashes the canonical review preimage", async () => {
  const review = await compilePreregistrationReview({
    record_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    revision: 1,
    title: "Review rehash safety",
    body: completeBody(),
  });
  const unsafe = structuredClone(review);
  unsafe.canonical_review_json = unsafe.canonical_review_json.replace(
    "Review rehash safety",
    "Review rehash changed",
  );

  await assert.rejects(
    compilePreregistrationHandoffManifest(unsafe),
    /PREREGISTRATION_HANDOFF_REVIEW_HASH_MISMATCH/u,
  );
});
