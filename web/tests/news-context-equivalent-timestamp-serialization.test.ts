import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const base: NewsTemporalObservation = {
  canonical_id: "event-equivalent-publication",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

test("equivalent publication timestamp serializations do not create source disagreement", () => {
  const equivalentDuplicate = {
    ...base,
    source: "source-b",
    published_at: "2026-09-07T10:00:00+01:00",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;

  const forward = replayNewsContextAt([base, equivalentDuplicate], "2026-09-07T09:30:00Z");
  const reverse = replayNewsContextAt([equivalentDuplicate, base], "2026-09-07T09:30:00Z");

  assert.deepEqual(forward, reverse);
  assert.equal(forward.interval_state, "events_present");
  assert.equal(forward.decisions.length, 1);
  assert.equal(forward.decisions[0].status, "admissible");
  assert.equal(forward.decisions[0].reason, "known_at_decision_time");
});
