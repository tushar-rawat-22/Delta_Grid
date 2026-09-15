import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const base: NewsTemporalObservation = {
  canonical_id: "event-degraded-matrix",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

const decisionTime = "2026-09-07T09:30:00Z";

function replay(observations: readonly NewsTemporalObservation[]) {
  return replayNewsContextAt(observations, decisionTime);
}

test("degraded source and mapping states remain explicit and unavailable", () => {
  const cases: ReadonlyArray<{
    name: string;
    patch: Partial<NewsTemporalObservation>;
    reason: string;
  }> = [
    { name: "stale source", patch: { source_state: "stale" }, reason: "source_stale" },
    { name: "missing source", patch: { source_state: "missing" }, reason: "source_missing" },
    {
      name: "conflicting source state",
      patch: { source_state: "disagreement" },
      reason: "source_disagreement",
    },
    {
      name: "ambiguous entity mapping",
      patch: { entity_mapping: "ambiguous" },
      reason: "ambiguous_entity_mapping",
    },
    {
      name: "missing entity mapping",
      patch: { entity_mapping: "missing" },
      reason: "missing_entity_mapping",
    },
    { name: "blank source identity", patch: { source: "   " }, reason: "missing_source_identity" },
  ];

  for (const item of cases) {
    const result = replay([{ ...base, ...item.patch }]);
    assert.equal(result.interval_state, "unavailable", item.name);
    assert.equal(result.decisions[0].status, "unavailable", item.name);
    assert.equal(result.decisions[0].reason, item.reason, item.name);
  }
});

test("partial collection cannot hide a degraded event behind an available event", () => {
  const available = { ...base, canonical_id: "event-available" } satisfies NewsTemporalObservation;
  const unavailable = {
    ...base,
    canonical_id: "event-unavailable",
    source: "source-b",
    source_state: "missing",
  } satisfies NewsTemporalObservation;

  const result = replay([available, unavailable]);

  assert.equal(result.interval_state, "events_present");
  assert.equal(result.decisions.length, 2);
  assert.deepEqual(
    result.decisions.map(({ canonical_id, status, reason }) => ({ canonical_id, status, reason })),
    [
      { canonical_id: "event-available", status: "admissible", reason: "known_at_decision_time" },
      { canonical_id: "event-unavailable", status: "unavailable", reason: "source_missing" },
    ],
  );
});

test("a future degraded observation cannot rewrite an earlier available historical state", () => {
  const futureDegraded = {
    ...base,
    source: "source-b",
    first_seen_at: "2026-09-07T09:40:00Z",
    fetched_at: "2026-09-07T09:41:00Z",
    source_state: "missing",
  } satisfies NewsTemporalObservation;

  const earlier = replayNewsContextAt([base, futureDegraded], "2026-09-07T09:30:00Z");
  assert.equal(earlier.interval_state, "events_present");
  assert.equal(earlier.decisions[0].status, "admissible");
  assert.equal(earlier.decisions[0].reason, "known_at_decision_time");
  assert.deepEqual(earlier.decisions[0].sources, ["source-a"]);

  const later = replayNewsContextAt([base, futureDegraded], "2026-09-07T09:45:00Z");
  assert.equal(later.interval_state, "unavailable");
  assert.equal(later.decisions[0].status, "unavailable");
  assert.equal(later.decisions[0].reason, "retroactive_first_seen_conflict");
  assert.deepEqual(later.decisions[0].sources, ["source-a", "source-b"]);
});

test("empty collection stays no-events rather than masquerading as source availability", () => {
  const result = replay([]);
  assert.equal(result.interval_state, "no_events");
  assert.deepEqual(result.decisions, []);
});
