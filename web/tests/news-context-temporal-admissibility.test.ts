import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const base: NewsTemporalObservation = {
  canonical_id: "event-1",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

function decisionFor(
  observation: NewsTemporalObservation,
  decisionTime = "2026-09-07T09:10:00Z",
) {
  return replayNewsContextAt([observation], decisionTime).decisions[0];
}

test("first-seen time, not publication time, controls historical admissibility", () => {
  const beforeSeen = replayNewsContextAt([base], "2026-09-07T09:05:00Z");
  assert.equal(beforeSeen.decisions[0].status, "future");
  assert.equal(beforeSeen.decisions[0].reason, "future_first_seen");
  assert.equal(beforeSeen.interval_state, "no_events");

  const atSeen = replayNewsContextAt([base], "2026-09-07T09:10:00Z");
  assert.equal(atSeen.decisions[0].status, "admissible");

  // Mandatory negative control: a published-at-only resolver would admit the
  // event at 09:05 even though the actual replay correctly keeps it future.
  const publishedOnlyWouldAdmit =
    Date.parse(base.published_at!) <= Date.parse("2026-09-07T09:05:00Z");
  assert.equal(publishedOnlyWouldAdmit, true);
});

test("late arrival across a market-session boundary remains late", () => {
  const late = {
    ...base,
    canonical_id: "late-session-event",
    published_at: "2026-09-07T09:14:30Z",
    first_seen_at: "2026-09-07T09:16:20Z",
    fetched_at: "2026-09-07T09:17:00Z",
  } satisfies NewsTemporalObservation;

  assert.equal(decisionFor(late, "2026-09-07T09:15:00Z").status, "future");
  assert.equal(decisionFor(late, "2026-09-07T09:16:20Z").status, "admissible");
});

test("a later duplicate cannot rewrite first-seen provenance earlier", () => {
  const laterDuplicate = {
    ...base,
    source: "source-a-refetch",
    first_seen_at: "2026-09-07T09:05:00Z",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt([base, laterDuplicate], "2026-09-07T09:30:00Z");
  assert.equal(replay.decisions.length, 1);
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "retroactive_first_seen_conflict");
  assert.equal(replay.decisions[0].first_seen_at, base.first_seen_at);
});

test("ordinary duplicates canonicalize without moving the original first-seen time", () => {
  const refetch = {
    ...base,
    source: "source-a-refetch",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;
  const replay = replayNewsContextAt([refetch, base], "2026-09-07T09:30:00Z");

  assert.equal(replay.decisions.length, 1);
  assert.equal(replay.decisions[0].status, "admissible");
  assert.equal(replay.decisions[0].first_seen_at, base.first_seen_at);
});

test("invalid duplicate temporal provenance poisons the canonical event", () => {
  const malformedDuplicate = {
    ...base,
    source: "source-b",
    first_seen_at: "not-a-timestamp",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;
  const missingDuplicate = {
    ...base,
    source: "source-c",
    first_seen_at: null,
    fetched_at: "2026-09-07T09:21:00Z",
  } satisfies NewsTemporalObservation;
  const invertedDuplicate = {
    ...base,
    source: "source-d",
    first_seen_at: "2026-09-07T09:22:00Z",
    fetched_at: "2026-09-07T09:21:00Z",
  } satisfies NewsTemporalObservation;

  assert.equal(
    replayNewsContextAt([base, malformedDuplicate], "2026-09-07T09:30:00Z").decisions[0].reason,
    "malformed_temporal_provenance",
  );
  assert.equal(
    replayNewsContextAt([base, missingDuplicate], "2026-09-07T09:30:00Z").decisions[0].reason,
    "missing_temporal_provenance",
  );
  assert.equal(
    replayNewsContextAt([base, invertedDuplicate], "2026-09-07T09:30:00Z").decisions[0].reason,
    "inverted_temporal_provenance",
  );
});

test("duplicate immutable provenance disagreement remains explicit", () => {
  const changedPublication = {
    ...base,
    source: "source-b",
    published_at: "2026-09-07T09:00:30Z",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt([base, changedPublication], "2026-09-07T09:30:00Z");
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "source_disagreement");
});

test("missing, malformed and inverted timestamps fail closed", () => {
  assert.equal(
    decisionFor({ ...base, first_seen_at: null }).reason,
    "missing_temporal_provenance",
  );
  assert.equal(
    decisionFor({ ...base, first_seen_at: "2026-09-07 09:10:00" }).reason,
    "malformed_temporal_provenance",
  );
  assert.equal(
    decisionFor({ ...base, first_seen_at: "2026-09-07T08:59:00Z" }).reason,
    "inverted_temporal_provenance",
  );
  assert.equal(
    decisionFor({ ...base, fetched_at: "2026-09-07T09:09:59Z" }).reason,
    "inverted_temporal_provenance",
  );
});

test("entity and source uncertainty stay explicit and non-directional", () => {
  assert.equal(
    decisionFor({ ...base, entity_mapping: "ambiguous" }).reason,
    "ambiguous_entity_mapping",
  );
  assert.equal(
    decisionFor({ ...base, entity_mapping: "missing" }).reason,
    "missing_entity_mapping",
  );
  assert.equal(decisionFor({ ...base, source_state: "stale" }).reason, "source_stale");
  assert.equal(decisionFor({ ...base, source_state: "missing" }).reason, "source_missing");
  assert.equal(
    decisionFor({ ...base, source_state: "disagreement" }).reason,
    "source_disagreement",
  );
});

test("zero events and unavailable evidence are distinct interval states", () => {
  assert.equal(
    replayNewsContextAt([], "2026-09-07T09:10:00Z").interval_state,
    "no_events",
  );
  assert.equal(
    replayNewsContextAt(
      [{ ...base, source_state: "missing" }],
      "2026-09-07T09:10:00Z",
    ).interval_state,
    "unavailable",
  );
});

test("replay output is deterministic regardless of duplicate input order", () => {
  const refetch = {
    ...base,
    source: "source-z",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;

  const forward = replayNewsContextAt([base, refetch], "2026-09-07T09:30:00Z");
  const reverse = replayNewsContextAt([refetch, base], "2026-09-07T09:30:00Z");
  assert.deepEqual(forward, reverse);
});

test("equal-key conflicting duplicates fail closed identically in either input order", () => {
  const ambiguousDuplicate = {
    ...base,
    entity_mapping: "ambiguous",
  } satisfies NewsTemporalObservation;

  const forward = replayNewsContextAt([base, ambiguousDuplicate], "2026-09-07T09:30:00Z");
  const reverse = replayNewsContextAt([ambiguousDuplicate, base], "2026-09-07T09:30:00Z");

  assert.deepEqual(forward, reverse);
  assert.equal(forward.interval_state, "unavailable");
  assert.equal(forward.decisions[0].status, "unavailable");
  assert.equal(forward.decisions[0].reason, "source_disagreement");
});

test("decision time must itself carry an explicit UTC offset", () => {
  assert.throws(
    () => replayNewsContextAt([base], "2026-09-07 09:10:00"),
    /offset-aware ISO timestamp/,
  );
});
