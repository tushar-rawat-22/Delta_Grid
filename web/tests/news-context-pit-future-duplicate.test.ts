import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const known: NewsTemporalObservation = {
  canonical_id: "event-1",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

test("future duplicates cannot rewrite historical canonical state", () => {
  const futureConflict = {
    ...known,
    source: "source-b",
    published_at: "2026-09-07T09:00:30Z",
    first_seen_at: "2026-09-07T09:20:00Z",
    fetched_at: "2026-09-07T09:21:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt(
    [futureConflict, known],
    "2026-09-07T09:15:00Z",
  );

  assert.equal(replay.interval_state, "events_present");
  assert.equal(replay.decisions.length, 1);
  assert.equal(replay.decisions[0].status, "admissible");
  assert.equal(replay.decisions[0].reason, "known_at_decision_time");
  assert.equal(replay.decisions[0].first_seen_at, known.first_seen_at);
  assert.deepEqual(replay.decisions[0].sources, ["source-a"]);
});

test("entirely future duplicate groups remain future without disagreement leakage", () => {
  const futureA = {
    ...known,
    source: "source-a",
    first_seen_at: "2026-09-07T09:20:00Z",
    fetched_at: "2026-09-07T09:21:00Z",
  } satisfies NewsTemporalObservation;
  const futureB = {
    ...futureA,
    source: "source-b",
    published_at: "2026-09-07T09:00:30Z",
    fetched_at: "2026-09-07T09:22:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt([futureB, futureA], "2026-09-07T09:15:00Z");

  assert.equal(replay.interval_state, "no_events");
  assert.equal(replay.decisions.length, 1);
  assert.equal(replay.decisions[0].status, "future");
  assert.equal(replay.decisions[0].reason, "future_first_seen");
  assert.deepEqual(replay.decisions[0].sources, []);
});

test("unplaceable first-seen provenance still fails closed", () => {
  const malformed = {
    ...known,
    source: "source-b",
    first_seen_at: "not-a-timestamp",
    fetched_at: "2026-09-07T09:30:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt([known, malformed], "2026-09-07T09:15:00Z");

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "malformed_temporal_provenance");
});
