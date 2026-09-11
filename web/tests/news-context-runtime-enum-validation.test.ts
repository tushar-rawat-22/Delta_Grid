import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const base: NewsTemporalObservation = {
  canonical_id: "event-runtime-validation",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

function runtimeObservation(patch: Record<string, unknown>): NewsTemporalObservation {
  return { ...base, ...patch } as unknown as NewsTemporalObservation;
}

test("unknown entity mapping fails closed instead of becoming admissible", () => {
  const replay = replayNewsContextAt(
    [runtimeObservation({ entity_mapping: "provider-unknown" })],
    "2026-09-07T09:10:00Z",
  );

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "malformed_entity_mapping");
});

test("unknown source state fails closed with an explicit reason", () => {
  const replay = replayNewsContextAt(
    [runtimeObservation({ source_state: "provider-error" })],
    "2026-09-07T09:10:00Z",
  );

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "malformed_source_state");
});

test("known runtime states preserve ordinary admissibility", () => {
  const replay = replayNewsContextAt([base], "2026-09-07T09:10:00Z");

  assert.equal(replay.interval_state, "events_present");
  assert.equal(replay.decisions[0].status, "admissible");
  assert.equal(replay.decisions[0].reason, "known_at_decision_time");
});
