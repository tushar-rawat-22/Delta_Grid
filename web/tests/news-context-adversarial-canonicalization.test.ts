import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const decisionTime = "2026-09-07T09:30:00Z";
const base: NewsTemporalObservation = {
  canonical_id: "event-adversarial-canonicalization",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

function replay(observations: readonly NewsTemporalObservation[]) {
  return replayNewsContextAt(observations, decisionTime);
}

test("exact duplicate delivery is idempotent and does not manufacture extra evidence", () => {
  const result = replay([base, { ...base }]);

  assert.equal(result.interval_state, "events_present");
  assert.equal(result.decisions.length, 1);
  assert.deepEqual(result.decisions[0], {
    canonical_id: base.canonical_id,
    status: "admissible",
    reason: "known_at_decision_time",
    first_seen_at: base.first_seen_at,
    sources: ["source-a"],
  });
});

test("duplicate ordering cannot change the canonical replay decision", () => {
  const corroborating = {
    ...base,
    source: "source-b",
    fetched_at: "2026-09-07T09:12:00Z",
  } satisfies NewsTemporalObservation;

  const forward = replay([base, corroborating]);
  const reverse = replay([corroborating, base]);

  assert.deepEqual(reverse, forward);
  assert.equal(forward.decisions.length, 1);
  assert.deepEqual(forward.decisions[0].sources, ["source-a", "source-b"]);
});

test("conflicting published timestamps for one canonical event fail closed", () => {
  const conflict = {
    ...base,
    source: "source-b",
    published_at: "2026-09-07T09:01:00Z",
    fetched_at: "2026-09-07T09:12:00Z",
  } satisfies NewsTemporalObservation;

  const result = replay([base, conflict]);

  assert.equal(result.interval_state, "unavailable");
  assert.equal(result.decisions.length, 1);
  assert.equal(result.decisions[0].status, "unavailable");
  assert.equal(result.decisions[0].reason, "source_disagreement");
  assert.deepEqual(result.decisions[0].sources, ["source-a", "source-b"]);
});

test("conflicting entity mappings for one canonical event fail closed", () => {
  const conflict = {
    ...base,
    source: "source-b",
    fetched_at: "2026-09-07T09:12:00Z",
    entity_mapping: "ambiguous",
  } satisfies NewsTemporalObservation;

  const result = replay([base, conflict]);

  assert.equal(result.interval_state, "unavailable");
  assert.equal(result.decisions.length, 1);
  assert.equal(result.decisions[0].status, "unavailable");
  assert.equal(result.decisions[0].reason, "source_disagreement");
  assert.deepEqual(result.decisions[0].sources, ["source-a", "source-b"]);
});

test("a duplicate first seen only after the decision cannot leak backward", () => {
  const lateDuplicate = {
    ...base,
    source: "source-b",
    first_seen_at: "2026-09-07T09:40:00Z",
    fetched_at: "2026-09-07T09:41:00Z",
  } satisfies NewsTemporalObservation;

  const result = replay([lateDuplicate, base]);

  assert.equal(result.interval_state, "events_present");
  assert.equal(result.decisions.length, 1);
  assert.equal(result.decisions[0].status, "admissible");
  assert.equal(result.decisions[0].reason, "known_at_decision_time");
  assert.deepEqual(result.decisions[0].sources, ["source-a"]);
});
