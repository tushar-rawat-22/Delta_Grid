import assert from "node:assert/strict";
import test from "node:test";
import {
  replayNewsContextAt,
  type NewsTemporalObservation,
} from "../lib/news-context/temporal-admissibility.ts";

const base: NewsTemporalObservation = {
  canonical_id: "event-canonical-identity",
  source: "source-a",
  published_at: "2026-09-07T09:00:00Z",
  first_seen_at: "2026-09-07T09:10:00Z",
  fetched_at: "2026-09-07T09:11:00Z",
  entity_mapping: "resolved",
  source_state: "available",
};

const decisionTime = "2026-09-07T09:30:00Z";

function runtimeObservation(patch: Record<string, unknown>): NewsTemporalObservation {
  return { ...base, ...patch } as unknown as NewsTemporalObservation;
}

test("blank canonical identity fails closed instead of becoming evidence", () => {
  for (const canonicalId of ["", "   ", "\t"]) {
    const replay = replayNewsContextAt(
      [{ ...base, canonical_id: canonicalId }],
      decisionTime,
    );

    assert.equal(replay.interval_state, "unavailable");
    assert.equal(replay.decisions.length, 1);
    assert.equal(replay.decisions[0].status, "unavailable");
    assert.equal(replay.decisions[0].reason, "missing_canonical_identity");
  }
});

test("non-string canonical identity fails closed at the runtime boundary", () => {
  const replay = replayNewsContextAt(
    [runtimeObservation({ canonical_id: null })],
    decisionTime,
  );

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "missing_canonical_identity");
});

test("canonical identity whitespace cannot manufacture a second event", () => {
  const conflictingDuplicate = {
    ...base,
    canonical_id: "  event-canonical-identity\t",
    source: "source-b",
    published_at: "2026-09-07T09:00:30Z",
    fetched_at: "2026-09-07T09:12:00Z",
  } satisfies NewsTemporalObservation;

  const replay = replayNewsContextAt([base, conflictingDuplicate], decisionTime);

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions.length, 1);
  assert.equal(replay.decisions[0].canonical_id, base.canonical_id);
  assert.equal(replay.decisions[0].reason, "source_disagreement");
  assert.deepEqual(replay.decisions[0].sources, ["source-a", "source-b"]);
});

test("non-string source identity also fails closed instead of throwing", () => {
  const malformedDuplicate = runtimeObservation({
    source: null,
    fetched_at: "2026-09-07T09:12:00Z",
  });
  const replay = replayNewsContextAt(
    [base, malformedDuplicate],
    decisionTime,
  );

  assert.equal(replay.interval_state, "unavailable");
  assert.equal(replay.decisions.length, 1);
  assert.equal(replay.decisions[0].status, "unavailable");
  assert.equal(replay.decisions[0].reason, "missing_source_identity");
  assert.deepEqual(replay.decisions[0].sources, ["source-a"]);
});
