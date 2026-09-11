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
    | "malformed_entity_mapping"
    | "missing_source_identity"
    | "source_stale"
    | "source_missing"
    | "source_disagreement"
    | "malformed_source_state";
  first_seen_at: string | null;
  sources: readonly string[];
}>;

type NewsTemporalDecisionWithoutSources = Omit<NewsTemporalDecision, "sources">;

export type NewsTemporalReplay = Readonly<{
  decision_time: string;
  interval_state: "events_present" | "no_events" | "unavailable";
  decisions: readonly NewsTemporalDecision[];
}>;

// Date.parse() only preserves millisecond precision. Accepting additional
// fractional digits would silently collapse distinct source timestamps and
// could hide temporal/source disagreement, so unsupported precision fails closed.
const ISO_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(Z|[+-](\d{2}):(\d{2}))$/;
const ENTITY_MAPPING_STATES = new Set<EntityMappingState>(["resolved", "ambiguous", "missing"]);
const SOURCE_STATES = new Set<SourceState>(["available", "stale", "missing", "disagreement"]);

function parseTimestamp(value: string | null): number | null {
  if (value === null) return null;

  const match = value.match(ISO_TIMESTAMP);
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

function canonicalSourceIdentity(value: string): string | null {
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function temporalFailure(
  observation: NewsTemporalObservation,
): NewsTemporalDecisionWithoutSources | null {
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
): NewsTemporalDecisionWithoutSources | null {
  if (canonicalSourceIdentity(observation.source) === null) {
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: "missing_source_identity",
      first_seen_at: observation.first_seen_at,
    };
  }
  if (!ENTITY_MAPPING_STATES.has(observation.entity_mapping)) {
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: "malformed_entity_mapping",
      first_seen_at: observation.first_seen_at,
    };
  }
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
  if (!SOURCE_STATES.has(observation.source_state)) {
    return {
      canonical_id: observation.canonical_id,
      status: "unavailable",
      reason: "malformed_source_state",
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
  const aSource = canonicalSourceIdentity(a.source) ?? a.source;
  const bSource = canonicalSourceIdentity(b.source) ?? b.source;
  return (
    aKey - bKey ||
    aSource.localeCompare(bSource) ||
    compareNullableText(a.first_seen_at, b.first_seen_at) ||
    compareNullableText(a.published_at, b.published_at) ||
    compareNullableText(a.fetched_at, b.fetched_at) ||
    a.entity_mapping.localeCompare(b.entity_mapping) ||
    a.source_state.localeCompare(b.source_state) ||
    a.canonical_id.localeCompare(b.canonical_id)
  );
}

function canonicalSources(
  observations: readonly NewsTemporalObservation[],
  canonicalId: string,
  decisionTime: number,
): readonly string[] {
  return [...new Set(
    observations
      .filter((observation) => observation.canonical_id === canonicalId)
      .filter((observation) => {
        const firstSeen = parseTimestamp(observation.first_seen_at);
        return firstSeen !== null && !Number.isNaN(firstSeen) && firstSeen <= decisionTime;
      })
      .map((observation) => canonicalSourceIdentity(observation.source))
      .filter((source): source is string => source !== null),
  )].sort((a, b) => a.localeCompare(b));
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

    const missingSourceIdentity = [...group]
      .filter((candidate) => canonicalSourceIdentity(candidate.source) === null)
      .sort(deterministicObservationOrder)[0];
    if (missingSourceIdentity) {
      result.push(missingSourceIdentity);
      continue;
    }

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

function observationsKnownAtDecisionTime(
  observations: readonly NewsTemporalObservation[],
  decisionTime: number,
): readonly NewsTemporalObservation[] {
  const grouped = new Map<string, NewsTemporalObservation[]>();
  for (const observation of observations) {
    const group = grouped.get(observation.canonical_id) ?? [];
    group.push(observation);
    grouped.set(observation.canonical_id, group);
  }

  const result: NewsTemporalObservation[] = [];
  for (const group of grouped.values()) {
    const knownOrUnplaceable = group.filter((observation) => {
      const firstSeen = parseTimestamp(observation.first_seen_at);
      return firstSeen === null || Number.isNaN(firstSeen) || firstSeen <= decisionTime;
    });

    if (knownOrUnplaceable.length > 0) {
      result.push(...knownOrUnplaceable);
      continue;
    }

    // The event exists in the source history but every valid observation was
    // first seen after the decision time. Keep one deterministic representative
    // so replay preserves the existing future/no_events result without letting
    // future duplicate disagreement leak backward into historical state.
    result.push([...group].sort(deterministicObservationOrder)[0]);
  }

  return result;
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

  const replayObservations = observationsKnownAtDecisionTime(observations, parsedDecisionTime);
  const decisions = canonicalize(replayObservations).map((observation): NewsTemporalDecision => {
    const sources = canonicalSources(replayObservations, observation.canonical_id, parsedDecisionTime);
    const temporal = temporalFailure(observation);
    if (temporal) return { ...temporal, sources };

    const uncertainty = uncertaintyFailure(observation);
    if (uncertainty) {
      if (
        uncertainty.reason === "source_disagreement" &&
        replayObservations.filter((item) => item.canonical_id === observation.canonical_id).length > 1
      ) {
        const firstSeenValues = replayObservations
          .filter((item) => item.canonical_id === observation.canonical_id)
          .map((item) => parseTimestamp(item.first_seen_at))
          .filter((value): value is number => value !== null && !Number.isNaN(value));
        const canonicalFirstSeen = parseTimestamp(observation.first_seen_at)!;
        if (firstSeenValues.some((value) => value !== canonicalFirstSeen)) {
          return {
            ...uncertainty,
            reason: "retroactive_first_seen_conflict",
            sources,
          };
        }
      }
      return { ...uncertainty, sources };
    }

    const firstSeen = parseTimestamp(observation.first_seen_at)!;
    if (firstSeen > parsedDecisionTime) {
      return {
        canonical_id: observation.canonical_id,
        status: "future",
        reason: "future_first_seen",
        first_seen_at: observation.first_seen_at,
        sources,
      };
    }

    return {
      canonical_id: observation.canonical_id,
      status: "admissible",
      reason: "known_at_decision_time",
      first_seen_at: observation.first_seen_at,
      sources,
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
