import assert from "node:assert/strict";
import test from "node:test";

import { createHypothesisSeed } from "../research-app/src/hypothesis-model.ts";
import {
  compilePreregistrationReview,
  PREREGISTRATION_AUTHORITY,
  PREREGISTRATION_BOUNDARY,
  PREREGISTRATION_HEADINGS,
  PREREGISTRATION_TERMINAL_HEADING,
} from "../research-app/src/preregistration-model.ts";

const priority = {
  kind: "SEVEN_DAY_VOLATILITY",
  instrument_id: "CRYPTO_BTC_USD",
  symbol: "BTC",
  metric: "realized_volatility_7d",
  value: 0.42,
  detail_code: "COLLECTION_SUCCEEDED",
  latest_observed_at: "2026-08-15T05:00:00.000Z",
};

test("seeded thesis is deliberately not structurally lock-ready", async () => {
  const seed = createHypothesisSeed(priority);
  const review = await compilePreregistrationReview({
    record_id: "11111111-1111-4111-8111-111111111111",
    revision: 1,
    title: seed.title,
    body: seed.body,
  });

  assert.equal(review.structural_lock_ready, false);
  assert.ok(review.blocking_reasons.length > 0);
  assert.equal(review.boundary, PREREGISTRATION_BOUNDARY);
  assert.equal(review.authority_effect, PREREGISTRATION_AUTHORITY);
  assert.deepEqual(review.side_effects, {
    persistence: false,
    trial_reserved: false,
    permit_consumed: false,
    execution_authorized: false,
    protected_evidence_opened: false,
    mission104_authorized: false,
    trading_authorized: false,
  });
});

test("complete scientific sections receive deterministic identity only", async () => {
  const body = PREREGISTRATION_HEADINGS.map(
    (heading, index) => `${heading}\nFounder declaration ${index + 1}.`,
  ).join("\n\n");

  const input = {
    record_id: "22222222-2222-4222-8222-222222222222",
    revision: 4,
    title: "BTC causal mechanism",
    body,
  };

  const first = await compilePreregistrationReview(input);
  const second = await compilePreregistrationReview(input);

  assert.equal(first.structural_lock_ready, true);
  assert.deepEqual(first.blocking_reasons, []);
  assert.equal(first.canonical_review_hash_sha256, second.canonical_review_hash_sha256);
  assert.equal(first.review_id, second.review_id);
  assert.match(first.canonical_review_hash_sha256, /^[0-9a-f]{64}$/u);
  assert.equal(first.canonical_bindings.development_dataset.owner, "M101_DATASET_DESCRIPTOR");
  assert.equal(first.canonical_bindings.development_permit.owner, "M101_DEVELOPMENT_PERMIT");
  assert.equal(first.canonical_bindings.trial_budget_and_reservation.owner, "M94_TRIAL_LEDGER_VIA_M101");
  assert.equal(first.canonical_bindings.execution_family_and_variant.owner, "M102_SEALED_EXPERIMENT_REGISTRY");
  assert.equal(first.canonical_bindings.statistical_program.owner, "M103_PROGRAM_PROTOCOL");
  assert.ok(
    Object.values(first.canonical_bindings).every(
      (binding) => binding.status === "UNRESOLVED" && binding.browser_writable === false,
    ),
  );
});

test("system handoff after next review is metadata, not founder protocol content", async () => {
  const scientificBody = PREREGISTRATION_HEADINGS.map(
    (heading, index) => `${heading}\nFounder declaration ${index + 1}.`,
  ).join("\n\n");
  const body = [
    scientificBody,
    "",
    PREREGISTRATION_TERMINAL_HEADING,
    "[System: canonical authority remains outside the notebook.]",
  ].join("\n");

  const review = await compilePreregistrationReview({
    record_id: "44444444-4444-4444-8444-444444444444",
    revision: 1,
    title: "SOL causal mechanism",
    body,
  });

  assert.equal(review.structural_lock_ready, true);
  assert.deepEqual(review.blocking_reasons, []);
  assert.equal(
    review.scientific_protocol["NEXT REVIEW"],
    "Founder declaration 10.",
  );
  assert.equal(
    review.canonical_review_json.includes("canonical authority remains outside the notebook"),
    false,
  );
});

test("scientific identity changes when thesis revision or content changes", async () => {
  const body = PREREGISTRATION_HEADINGS.map(
    (heading, index) => `${heading}\nFounder declaration ${index + 1}.`,
  ).join("\n\n");

  const base = {
    record_id: "33333333-3333-4333-8333-333333333333",
    revision: 1,
    title: "ETH causal mechanism",
    body,
  };

  const first = await compilePreregistrationReview(base);
  const revised = await compilePreregistrationReview({ ...base, revision: 2 });
  const changed = await compilePreregistrationReview({
    ...base,
    body: body.replace("Founder declaration 1.", "Founder declaration changed."),
  });

  assert.notEqual(first.review_id, revised.review_id);
  assert.notEqual(first.review_id, changed.review_id);
});
