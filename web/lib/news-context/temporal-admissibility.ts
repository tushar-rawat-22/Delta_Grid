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

const ISO_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?(Z|[+-](\d{2}):(\d{2}))$/;

function parseTimestamp(value: string | null): number | null {
  if (value === null) return null;

  const match = ISO_TIMESTAMP.exec(value);
  if (!match) return Number.NaN;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = match[8] === "Z" ? 0 : Number(match[9]);
  const offsetMinute = match[8] === "Z" ? 0 : Number(match[10]);

  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth[month - 1] ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59
  ) {
    return Number.NaN;
  }

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

function compareNullableText(a: string | null, b: string | null): number {
  if (a === b) return 0;
  if (a === null) return -1;
  if (b === null) return 1;
  return a.localeCompare(b);
}

function deterministicObservationOrder(
  a: NewsTemporalObservation,
  b: NewsTemporalObservation,
): number {
  const aFetched = parseTimestamp(a.fetched_at);
  const bFetched = parseTimestamp(b.fetched_at);
  const aKey = aFetched === null || Number.isNaN(aFetched) ? Number.POSITIVE_INFINITY : aFetched;
  const bKey = bFetched === null || Number.isNaN(bFetched) ? Number.POSITIVE_INFINITY : bFetched;
  return (
    aKey - bKey ||
    a.source.localeCompare(b.source) ||
    compareNullableText(a.first_seen_at, b.first_seen_at) ||
    compareNullableText(a.published_at, b.published_at) ||
    compareNullableText(a.fetched_at, b.fetched_at) ||
    a.entity_mapping.localeCompare(b.entity_mapping) ||
    a.source_state.localeCompare(b.source_state) ||
    a.canonical_id.localeCompare(b.canonical_id)
  );
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
    const sorted = [...group].sort(deterministicObservationOrder);

    // A duplicate with broken temporal provenance cannot be hidden by a valid
    // earlier fetch. Preserve one deterministic invalid observation so the
    // canonical event fails closed in temporalFailure().
    const invalid = [...group]
      .filter((candidate) => temporalFailure(candidate) !== null)
      .sort(deterministicObservationOrder)[0];
    if (invalid) {
      result.push(invalid);
      continue;
    }

    const anchor = sorted[0];
    const anchorFirstSeen = parseTimestamp(anchor.first_seen_at)!;
    const firstSeenConflict = sorted.slice(1).some(
      (candidate) => parseTimestamp(candidate.first_seen_at)! !== anchorFirstSeen,
    );

    if (firstSeenConflict) {
      result.push({
        ...anchor,
        canonical_id: canonicalId,
        source_state: "disagreement",
      });
      continue;
    }

    const anchorPublished = parseTimestamp(anchor.published_at)!;
    const immutableConflict = sorted.slice(1).some(
      (candidate) =>
        parseTimestamp(candidate.published_at)! !== anchorPublished ||
        candidate.entity_mapping !== anchor.entity_mapping ||
        candidate.source_state !== anchor.source_state,
    );
    if (immutableConflict) {
      result.push({
        ...anchor,
        canonical_id: canonicalId,
        entity_mapping: "resolved",
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
        const canonicalFirstSeen = parseTimestamp(observation.first_seen_at)!;
        if (firstSeenValues.some((value) => value !== canonicalFirstSeen)) {
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
