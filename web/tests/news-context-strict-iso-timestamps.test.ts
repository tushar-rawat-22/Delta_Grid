import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const base: NewsTemporalObservation = {
  canonical_id: "event-strict-timestamp",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

test("impossible calendar dates fail closed instead of being normalized by Date.parse", () => {
  const replay = replayNewsContextAt(
    [{ ...base, published_at: "2026-02-30T09:00:00Z" }],
    "2026-09-07T09:30:00Z",
  );

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "malformed_temporal_provenance");
});

test("timestamp provenance requires an ISO T separator", () => {
  const replay = replayNewsContextAt(
    [{ ...base, first_seen_at: "2026-09-07 09:10:00Z" }],
    "2026-09-07T09:30:00Z",
  );

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "malformed_temporal_provenance");
});

test("sub-millisecond source timestamps fail closed instead of collapsing in Date.parse", () => {
  const replay = replayNewsContextAt(
    [{ ...base, published_at: "2026-09-07T09:00:00.123456Z" }],
    "2026-09-07T09:30:00Z",
  );

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "malformed_temporal_provenance");
});

test("millisecond timestamp precision remains admissible", () => {
  const replay = replayNewsContextAt(
    [
      {
        ...base,
        published_at: "2026-09-07T09:00:00.123Z",
        first_seen_at: "2026-09-07T09:10:00.456Z",
        fetched_at: "2026-09-07T09:11:00.789Z",
      },
    ],
    "2026-09-07T09:30:00.000Z",
  );

  assert.equal(replay.interval_state, "events_present");
  assert.equal(replay.decisions[0].status, "admissible");
});

test("decision time rejects impossible calendar dates", () => {
  assert.throws(
    () => replayNewsContextAt([base], "2026-02-30T09:30:00Z"),
    /offset-aware ISO timestamp/,
  );
});

test("decision time rejects non-ISO space-separated timestamps even with an offset", () => {
  assert.throws(
    () => replayNewsContextAt([base], "2026-09-07 09:30:00Z"),
    /offset-aware ISO timestamp/,
  );
});

test("decision time rejects unsupported sub-millisecond precision", () => {
  assert.throws(
    () => replayNewsContextAt([base], "2026-09-07T09:30:00.123456Z"),
    /offset-aware ISO timestamp/,
  );
});
