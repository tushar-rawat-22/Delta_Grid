export type EntityMappingState = "resolved" | "ambiguous" | "missing";
export type SourceState = "available" | "stale" | "missing" | "disagreement";

export type NewsTemporalObservation = Readonly<{
  canonical_id: string;
  source: string;
  published_at: string | null;
  first_seen_at: string | null;
  fetched_at: string | null;
  entity_mapping: EntityMappingState;
  source_state: SourceState;
}>;

export type NewsTemporalDecision = Readonly<{
  canonical_id: string;
  status: "admissible" | "unavailable" | "future";
  reason:
    | "known_at_decision_time"
    | "future_first_seen"
    | "missing_temporal_provenance"
    | "malformed_temporal_provenance"
    | "inverted_temporal_provenance"
    | "retroactive_first_seen_conflict"
    | "ambiguous_entity_mapping"
    | "missing_entity_mapping"
    | "source_stale"
    | "source_missing"
    | "source_disagreement";
  first_seen_at: string | null;
}>;

export type NewsTemporalReplay = Readonly<{
  decision_time: string;
  interval_state: "events_present" | "no_events" | "unavailable";
  decisions: readonly NewsTemporalDecision[];
}>;

function parseTimestamp(value: string | null): number | null {
  if (value === null) return null;
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return Number.NaN;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function temporalFailure(
  observation: NewsTemporalObservation,
): NewsTemporalDecision | null {
  const published = parseTimestamp(observation.published_at);
  const firstSeen = parseTimestamp(observation.first_seen_at);
  const fetched = parseTimestamp(observation.fetched_at);

  if (published === null || firstSeen === null || fetched === null) {
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: "missing_temporal_provenance",
      first_seen_at: observation.first_seen_at,
    };
  }
  if ([published, firstSeen, fetched].some(Number.isNaN)) {
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: "malformed_temporal_provenance",
      first_seen_at: observation.first_seen_at,
    };
  }
  if (!(published <= firstSeen && firstSeen <= fetched)) {
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: "inverted_temporal_provenance",
      first_seen_at: observation.first_seen_at,
    };
  }
  return null;
}

function uncertaintyFailure(
  observation: NewsTemporalObservation,
): NewsTemporalDecision | null {
  if (observation.entity_mapping === "ambiguous") {
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: "ambiguous_entity_mapping",
      first_seen_at: observation.first_seen_at,
    };
  }
  if (observation.entity_mapping === "missing") {
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: "missing_entity_mapping",
      first_seen_at: observation.first_seen_at,
    };
  }
  if (observation.source_state !== "available") {
    const reason = {
      stale: "source_stale",
      missing: "source_missing",
      disagreement: "source_disagreement",
    } as const;
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: reason[observation.source_state],
      first_seen_at: observation.first_seen_at,
    };
  }
  return null;
}

function canonicalize(
  observations: readonly NewsTemporalObservation[],
): readonly NewsTemporalObservation[] {
  const grouped = new Map<string, NewsTemporalObservation[]>();
  for (const observation of observations) {
    const group = grouped.get(observation.canonical_id) ?? [];
    group.push(observation);
    grouped.set(observation.canonical_id, group);
  }

  const result: NewsTemporalObservation[] = [];
  for (const [canonicalId, group] of grouped) {
    const sorted = [...group].sort((a, b) => {
      const aFetched = parseTimestamp(a.fetched_at);
      const bFetched = parseTimestamp(b.fetched_at);
      const aKey = aFetched === null || Number.isNaN(aFetched) ? Number.POSITIVE_INFINITY : aFetched;
      const bKey = bFetched === null || Number.isNaN(bFetched) ? Number.POSITIVE_INFINITY : bFetched;
      return aKey - bKey || a.source.localeCompare(b.source);
    });

    const anchor = sorted[0];
    const anchorFirstSeen = parseTimestamp(anchor.first_seen_at);
    const retroactive = sorted.slice(1).some((candidate) => {
      const candidateFirstSeen = parseTimestamp(candidate.first_seen_at);
      return (
        anchorFirstSeen !== null &&
        !Number.isNaN(anchorFirstSeen) &&
        candidateFirstSeen !== null &&
        !Number.isNaN(candidateFirstSeen) &&
        candidateFirstSeen < anchorFirstSeen
      );
    });

    if (retroactive) {
      result.push({
        ...anchor,
        canonical_id: canonicalId,
        source_state: "disagreement",
      });
      continue;
    }
    result.push(anchor);
  }

  return result.sort((a, b) => a.canonical_id.localeCompare(b.canonical_id));
}

export function replayNewsContextAt(
  observations: readonly NewsTemporalObservation[],
  decisionTime: string,
): NewsTemporalReplay {
  const parsedDecisionTime = parseTimestamp(decisionTime);
  if (parsedDecisionTime === null || Number.isNaN(parsedDecisionTime)) {
    throw new TypeError("decisionTime must be an offset-aware ISO timestamp");
  }

  if (observations.length === 0) {
    return { decision_time: decisionTime, interval_state: "no_events", decisions: [] };
  }

  const decisions = canonicalize(observations).map((observation): NewsTemporalDecision => {
    const temporal = temporalFailure(observation);
    if (temporal) return temporal;

    const uncertainty = uncertaintyFailure(observation);
    if (uncertainty) {
      if (
        uncertainty.reason === "source_disagreement" &&
        observations.filter((item) => item.canonical_id === observation.canonical_id).length > 1
      ) {
        const firstSeenValues = observations
          .filter((item) => item.canonical_id === observation.canonical_id)
          .map((item) => parseTimestamp(item.first_seen_at))
          .filter((value): value is number => value !== null && !Number.isNaN(value));
        const fetchedValues = observations
          .filter((item) => item.canonical_id === observation.canonical_id)
          .map((item) => parseTimestamp(item.fetched_at))
          .filter((value): value is number => value !== null && !Number.isNaN(value));
        if (
          firstSeenValues.length > 1 &&
          fetchedValues.length > 1 &&
          Math.min(...firstSeenValues) < parseTimestamp(observation.first_seen_at)!
        ) {
          return {
            ...uncertainty,
            reason: "retroactive_first_seen_conflict",
          };
        }
      }
      return uncertainty;
    }

    const firstSeen = parseTimestamp(observation.first_seen_at)!;
    if (firstSeen > parsedDecisionTime) {
      return {
        canonical_id: observation.canonical_id,
        status: "future",
        reason: "future_first_seen",
        first_seen_at: observation.first_seen_at,
      };
    }

    return {
      canonical_id: observation.canonical_id,
      status: "admissible",
      reason: "known_at_decision_time",
      first_seen_at: observation.first_seen_at,
    };
  });

  const intervalState = decisions.some((item) => item.status === "admissible")
    ? "events_present"
    : decisions.every((item) => item.status === "future")
      ? "no_events"
      : "unavailable";

  return {
    decision_time: decisionTime,
    interval_state: intervalState,
    decisions,
  };
}
