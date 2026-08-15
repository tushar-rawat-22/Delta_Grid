import assert from "node:assert/strict";
import test from "node:test";

import {
  createHypothesisSeed,
} from "../research-app/src/hypothesis-model.ts";

test(
  "intelligence priority becomes a structured draft thesis only",
  () => {
    const seed = createHypothesisSeed({
      kind: "SEVEN_DAY_VOLATILITY",
      instrument_id: "CRYPTO_BTC_USD",
      symbol: "BTC",
      metric: "realized_volatility_7d",
      value: 0.42,
      detail_code: "COLLECTION_SUCCEEDED",
      latest_observed_at:
        "2026-08-15T05:00:00.000Z",
    });

    assert.equal(
      seed.record_type,
      "THESIS",
    );

    assert.equal(
      seed.status,
      "DRAFT",
    );

    assert.equal(
      seed.confidence,
      null,
    );

    assert.equal(
      seed.instrument_id,
      "CRYPTO_BTC_USD",
    );

    for (const heading of [
      "OBSERVATION",
      "ECONOMIC MECHANISM",
      "FALSIFICATION CONDITION",
      "DATA AND CHRONOLOGY",
      "TEST PLAN",
      "CANDIDATE AND PARAMETER BUDGET",
      "COST AND EXECUTION ASSUMPTIONS",
      "MULTIPLE-TESTING FAMILY",
      "SUCCESS AND FAILURE RULE",
      "NEXT REVIEW",
    ]) {
      assert.ok(
        seed.body.includes(heading),
      );
    }

    assert.ok(
      seed.tags.length <= 12,
    );

    assert.ok(
      seed.tags.every(
        (tag) =>
          tag.length >= 1 &&
          tag.length <= 32,
      ),
    );

    assert.equal(
      "signal" in seed,
      false,
    );

    assert.equal(
      "order" in seed,
      false,
    );

    assert.equal(
      "allocation" in seed,
      false,
    );
  },
);
