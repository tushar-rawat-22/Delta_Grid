import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const base: NewsTemporalObservation = {
  canonical_id: "event-source-id",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

test("blank source identity fails closed and is not counted as provenance", () => {
  for (const source of ["", "   ", "\t"]) {
    const replay = replayNewsContextAt([{ ...base, source }], "2026-09-07T09:10:00Z");
    assert.equal(replay.interval_state, "unavailable");
    assert.equal(replay.decisions[0].status, "unavailable");
    assert.equal(replay.decisions[0].reason, "missing_source_identity");
    assert.deepEqual(replay.decisions[0].sources, []);
  }
});

test("a later duplicate with missing source identity poisons the canonical event", () => {
  const unattributedDuplicate = {
    ...base,
    source: "   ",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt([base, unattributedDuplicate], "2026-09-07T09:30:00Z");
  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions.length, 1);
  assert.equal(replay.decisions[0].reason, "missing_source_identity");
  assert.deepEqual(replay.decisions[0].sources, ["source-a"]);
});

test("valid source identity remains deterministic", () => {
  const secondSource = {
    ...base,
    source: "source-z",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt([secondSource, base], "2026-09-07T09:30:00Z");
  assert.equal(replay.decisions[0].status, "admissible");
  assert.deepEqual(replay.decisions[0].sources, ["source-a", "source-z"]);
});

test("source identity whitespace cannot manufacture source diversity", () => {
  const paddedDuplicate = {
    ...base,
    source: "  source-a\t",
    fetched_at: "2026-09-07T09:20:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt([paddedDuplicate, base], "2026-09-07T09:30:00Z");
  assert.equal(replay.decisions[0].status, "admissible");
  assert.deepEqual(replay.decisions[0].sources, ["source-a"]);
});
