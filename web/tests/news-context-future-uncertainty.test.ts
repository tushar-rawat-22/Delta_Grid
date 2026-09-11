import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const future: NewsTemporalObservation = {
  canonical_id: "event-future",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:20:00Z",
  fetched_at: "2026-09-07T09:21:00Z",
  entity_mapping: "ambiguous",
  source_state: "stale",
};

test("wholly future uncertainty cannot poison an earlier historical replay", () => {
  const replay = replayNewsContextAt([future], "2026-09-07T09:15:00Z");

  assert.equal(replay.interval_state, "no_events");
  assert.equal(replay.decisions.length, 1);
  assert.equal(replay.decisions[0].status, "future");
  assert.equal(replay.decisions[0].reason, "future_first_seen");
  assert.deepEqual(replay.decisions[0].sources, []);
});
