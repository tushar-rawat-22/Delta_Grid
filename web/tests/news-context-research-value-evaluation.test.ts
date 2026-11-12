import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  NEWS_CONTEXT_RESEARCH_VALUE_CONTRACT_ID,
  NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS,
  evaluateNewsContextResearchValue,
  type NewsContextResearchValueEvidence,
  type NewsResearchEvaluationPartition,
  type NewsResearchResult,
  type NewsResearchVariant,
} from "../lib/news-context/research-value-evaluation.ts";

const H = (character: string) => character.repeat(64);
const VARIANT_SPEC: Record<NewsResearchVariant, string> = {
  baseline: H("1"),
  baseline_plus_feature: H("2"),
  lagged: H("3"),
  shuffled: H("4"),
  placebo: H("5"),
};
const DATASET = {
  train: H("a"),
  validation: H("b"),
  holdout: H("c"),
} as const;
const COST_MODEL = H("d");
const ROUND_TRIP_COST_BPS = 26;
const RESULT_HASH_CHARACTER: Record<NewsResearchEvaluationPartition, Record<NewsResearchVariant, string>> = {
  validation: {
    baseline: "a",
    baseline_plus_feature: "b",
    lagged: "c",
    shuffled: "d",
    placebo: "e",
  },
  holdout: {
    baseline: "f",
    baseline_plus_feature: "0",
    lagged: "1",
    shuffled: "2",
    placebo: "3",
  },
};

function result(
  partition: NewsResearchEvaluationPartition,
  variant: NewsResearchVariant,
  grossReturnBps: number,
): NewsResearchResult {
  const roundTripCount = 2;
  const assessedCostBps = roundTripCount * ROUND_TRIP_COST_BPS;
  return {
    partition,
    variant,
    variant_spec_sha256: VARIANT_SPEC[variant],
    cost_model_sha256: COST_MODEL,
    dataset_sha256: DATASET[partition],
    result_sha256: H(RESULT_HASH_CHARACTER[partition][variant]),
    evaluated_at: partition === "validation"
      ? "2026-01-02T00:00:00Z"
      : "2026-01-04T00:00:00Z",
    sample_count: 100,
    round_trip_count: roundTripCount,
    gross_return_bps: grossReturnBps,
    assessed_cost_bps: assessedCostBps,
    net_return_bps: grossReturnBps - assessedCostBps,
  };
}

function validEvidence(): NewsContextResearchValueEvidence {
  const gross = {
    validation: {
      baseline: 100,
      baseline_plus_feature: 140,
      lagged: 110,
      shuffled: 90,
      placebo: 80,
    },
    holdout: {
      baseline: 90,
      baseline_plus_feature: 130,
      lagged: 100,
      shuffled: 85,
      placebo: 75,
    },
  } as const;
  return {
    contract_id: NEWS_CONTEXT_RESEARCH_VALUE_CONTRACT_ID,
    contract_version: 1,
    frozen_at: "2026-01-01T00:00:00Z",
    claim: {
      scope: "bounded_comparative_evidence_only",
      performance_claim: "none",
      authority_effect: "none",
    },
    provenance: {
      code_sha256: H("6"),
      dataset_manifest_sha256: H("7"),
      feature_source_sha256: H("8"),
      frozen_protocol_sha256: H("f"),
    },
    protocol: {
      selection_partition: "validation",
      holdout_used_for_selection: false,
      minimum_sample_count: 100,
      label_horizon_ms: 3_600_000,
      feature_dependency_horizon_ms: 3_600_000,
      purge_ms: 3_600_000,
      embargo_ms: 3_600_000,
      baseline_spec_sha256: VARIANT_SPEC.baseline,
      feature_spec_sha256: VARIANT_SPEC.baseline_plus_feature,
      lagged_spec_sha256: VARIANT_SPEC.lagged,
      lag_ms: 7_200_000,
      shuffled_spec_sha256: VARIANT_SPEC.shuffled,
      shuffle_seed: 11,
      placebo_spec_sha256: VARIANT_SPEC.placebo,
      placebo_seed: 12,
    },
    costs: {
      model_sha256: COST_MODEL,
      provenance_sha256: H("9"),
      fixed_at: "2025-12-31T00:00:00Z",
      fee_bps_per_side: 10,
      spread_bps_round_trip: 2,
      slippage_bps_round_trip: 3,
      liquidity_impact_bps_round_trip: 1,
      max_participation_bps: 500,
      minimum_daily_notional_minor_units: 1_000_000,
    },
    partitions: [
      {
        name: "train",
        start: "2025-01-01T00:00:00Z",
        end: "2025-06-01T00:00:00Z",
        dataset_sha256: DATASET.train,
      },
      {
        name: "validation",
        start: "2025-06-03T00:00:00Z",
        end: "2025-08-01T00:00:00Z",
        dataset_sha256: DATASET.validation,
      },
      {
        name: "holdout",
        start: "2025-08-03T00:00:00Z",
        end: "2025-10-01T00:00:00Z",
        dataset_sha256: DATASET.holdout,
      },
    ],
    feature_availability: [
      {
        observation_id: "train-observation",
        partition: "train",
        source_provenance_sha256: H("0"),
        temporal_replay_sha256: H("4"),
        feature_available_at: "2025-03-01T09:00:00Z",
        transformed_at: "2025-03-01T09:01:00Z",
        decision_time: "2025-03-01T09:05:00Z",
      },
      {
        observation_id: "validation-observation",
        partition: "validation",
        source_provenance_sha256: H("0"),
        temporal_replay_sha256: H("4"),
        feature_available_at: "2025-07-01T09:00:00Z",
        transformed_at: "2025-07-01T09:01:00Z",
        decision_time: "2025-07-01T09:05:00Z",
      },
      {
        observation_id: "holdout-observation",
        partition: "holdout",
        source_provenance_sha256: H("0"),
        temporal_replay_sha256: H("4"),
        feature_available_at: "2025-09-01T09:00:00Z",
        transformed_at: "2025-09-01T09:01:00Z",
        decision_time: "2025-09-01T09:05:00Z",
      },
    ],
    holdout_opened_at: "2026-01-03T00:00:00Z",
    results: [
      ...NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS.map((variant) =>
        result("validation", variant, gross.validation[variant])
      ),
      ...NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS.map((variant) =>
        result("holdout", variant, gross.holdout[variant])
      ),
    ],
  };
}

type Mutable<T> = T extends readonly (infer Item)[]
  ? Mutable<Item>[]
  : T extends object
    ? { -readonly [Key in keyof T]: Mutable<T[Key]> }
    : T;

function mutableEvidence(): Mutable<NewsContextResearchValueEvidence> {
  return structuredClone(validEvidence()) as Mutable<NewsContextResearchValueEvidence>;
}

function setRuntimeField(target: object, key: string, value: unknown): void {
  (target as Record<string, unknown>)[key] = value;
}

test("complete synthetic comparative evidence is eligible only for bounded review", () => {
  const decision = evaluateNewsContextResearchValue(validEvidence());

  assert.equal(decision.status, "eligible_for_bounded_review");
  assert.deepEqual(decision.reasons, []);
  assert.deepEqual(decision.comparisons, [
    {
      partition: "validation",
      baseline_plus_feature_net_bps: 88,
      strongest_comparator_net_bps: 58,
      incremental_margin_bps: 30,
    },
    {
      partition: "holdout",
      baseline_plus_feature_net_bps: 78,
      strongest_comparator_net_bps: 48,
      incremental_margin_bps: 30,
    },
  ]);
  assert.equal(decision.performance_claim, "none");
  assert.equal(decision.authority_effect, "none");
});

test("missing provenance rejects otherwise favorable numbers", () => {
  const evidence = mutableEvidence();
  evidence.provenance.feature_source_sha256 = "";
  evidence.feature_availability[1].source_provenance_sha256 = "not-a-hash";

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("missing_provenance"));
});

test("feature availability after the decision time is temporal leakage", () => {
  const evidence = mutableEvidence();
  evidence.feature_availability[1].feature_available_at = "2025-07-01T09:06:00Z";

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("temporal_leakage"));
});

test("overlapping partitions and absent overlap protection fail closed", () => {
  const evidence = mutableEvidence();
  evidence.protocol.purge_ms = 0;
  evidence.protocol.embargo_ms = 0;
  evidence.partitions[1].start = evidence.partitions[0].end;

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("partition_order_violation"));
  assert(decision.reasons.includes("insufficient_purge_or_embargo"));
});

test("partition identities cannot alias across train, validation and holdout", () => {
  const evidence = mutableEvidence();
  evidence.partitions[2].dataset_sha256 = evidence.partitions[1].dataset_sha256;
  for (const resultRow of evidence.results) {
    if (resultRow.partition === "holdout") {
      resultRow.dataset_sha256 = evidence.partitions[1].dataset_sha256;
    }
  }

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("partition_identity_overlap"));
});

test("optimistic zero fees, spread and slippage are invalid costs", () => {
  const evidence = mutableEvidence();
  evidence.costs.fee_bps_per_side = 0;
  evidence.costs.spread_bps_round_trip = 0;
  evidence.costs.slippage_bps_round_trip = 0;

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("invalid_cost_assumptions"));
});

test("cost assumptions fixed after the protocol are rejected", () => {
  const evidence = mutableEvidence();
  evidence.costs.fixed_at = "2026-01-01T00:00:01Z";

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("invalid_cost_assumptions"));
});

test("cost accounting must reconcile gross, assessed costs and net", () => {
  const evidence = mutableEvidence();
  evidence.results[0].net_return_bps += 1;

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("result_accounting_mismatch"));
});

test("results below the frozen minimum sample count are rejected", () => {
  const evidence = mutableEvidence();
  evidence.protocol.minimum_sample_count = 101;

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("insufficient_sample_count"));
});

test("a missing shuffled control cannot pass the gate", () => {
  const evidence = mutableEvidence();
  evidence.results = evidence.results.filter(
    (item: NewsResearchResult) =>
      !(item.partition === "holdout" && item.variant === "shuffled"),
  );

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("missing_control_result"));
});

test("control specifications cannot alias one another", () => {
  const evidence = mutableEvidence();
  evidence.protocol.placebo_spec_sha256 = evidence.protocol.shuffled_spec_sha256;
  const placeboResult = evidence.results.find(
    (item: NewsResearchResult) => item.variant === "placebo",
  );
  assert(placeboResult);
  placeboResult.variant_spec_sha256 = evidence.protocol.shuffled_spec_sha256;

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("invalid_control_specification"));
});

test("the lagged control must cover the frozen feature dependency horizon", () => {
  const evidence = mutableEvidence();
  evidence.protocol.lag_ms = evidence.protocol.feature_dependency_horizon_ms - 1;

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("invalid_control_specification"));
});

test("holdout selection and pre-open holdout evidence are rejected", () => {
  const evidence = mutableEvidence();
  setRuntimeField(evidence.protocol, "holdout_used_for_selection", true);
  const prematureHoldout = evidence.results.find(
    (item: NewsResearchResult) => item.partition === "holdout",
  );
  assert(prematureHoldout);
  prematureHoldout.evaluated_at = "2026-01-02T12:00:00Z";

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("holdout_selection_violation"));
});

test("unsupported alpha or profitability claims are never emitted", () => {
  const evidence = mutableEvidence();
  setRuntimeField(evidence.claim, "performance_claim", "validated_alpha");

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("unsupported_performance_claim"));
  assert.equal(decision.performance_claim, "none");
  assert.equal(decision.authority_effect, "none");
});

test("undeclared authority claims cannot bypass the non-authorizing schema", () => {
  const evidence = mutableEvidence();
  setRuntimeField(evidence, "live_trading_authorized", true);

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("unexpected_evidence_field"));
});

test("feature evidence that does not beat the frozen controls is rejected", () => {
  const evidence = mutableEvidence();
  const resultRow = evidence.results.find(
    (item: NewsResearchResult) =>
      item.partition === "holdout" && item.variant === "baseline_plus_feature",
  );
  assert(resultRow);
  resultRow.gross_return_bps = 95;
  resultRow.net_return_bps = 43;

  const decision = evaluateNewsContextResearchValue(evidence);
  assert.equal(decision.status, "rejected");
  assert(decision.reasons.includes("feature_not_incremental"));
});

test("result ordering cannot change the deterministic decision", () => {
  const evidence = mutableEvidence();
  const forward = evaluateNewsContextResearchValue(evidence);
  evidence.results.reverse();
  evidence.feature_availability.reverse();
  const reverse = evaluateNewsContextResearchValue(evidence);

  assert.deepEqual(reverse, forward);
});

test("the machine contract preserves the non-authorizing ceiling", () => {
  const contract = JSON.parse(readFileSync(
    new URL("../../contracts/NEWS_CONTEXT_RESEARCH_VALUE_EVALUATION_V1.json", import.meta.url),
    "utf8",
  ));

  assert.equal(contract.contract_id, NEWS_CONTEXT_RESEARCH_VALUE_CONTRACT_ID);
  assert.deepEqual(contract.frozen_comparison.required_variants, NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS);
  assert.equal(contract.decision.performance_claim, "none");
  assert.equal(contract.decision.authority_effect, "none");
  assert(Object.values(contract.authority_ceiling).every((value) => value === false));
});

test("the validator has no network, process or execution surface", () => {
  const source = readFileSync(
    new URL("../lib/news-context/research-value-evaluation.ts", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(
    source,
    /\b(?:fetch|XMLHttpRequest|WebSocket|child_process|node:http|node:https|node:net)\b/u,
  );
});
