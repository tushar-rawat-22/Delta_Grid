export const NEWS_CONTEXT_RESEARCH_VALUE_CONTRACT_ID =
  "deltagrid-news-context-research-value-evaluation-v1";

export const NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS = [
  "baseline",
  "baseline_plus_feature",
  "lagged",
  "shuffled",
  "placebo",
] as const;

export type NewsResearchPartitionName = "train" | "validation" | "holdout";
export type NewsResearchEvaluationPartition = "validation" | "holdout";
export type NewsResearchVariant = (typeof NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS)[number];

export type NewsResearchValueRejectionReason =
  | "invalid_contract_identity"
  | "missing_provenance"
  | "invalid_frozen_protocol"
  | "invalid_partition_boundary"
  | "partition_order_violation"
  | "insufficient_purge_or_embargo"
  | "invalid_control_specification"
  | "invalid_cost_assumptions"
  | "temporal_leakage"
  | "holdout_selection_violation"
  | "missing_control_result"
  | "result_scope_mismatch"
  | "insufficient_sample_count"
  | "result_accounting_mismatch"
  | "unsupported_performance_claim"
  | "feature_not_incremental";

export type NewsResearchPartition = Readonly<{
  name: NewsResearchPartitionName;
  start: string;
  end: string;
  dataset_sha256: string;
}>;

export type NewsResearchCostAssumptions = Readonly<{
  model_sha256: string;
  provenance_sha256: string;
  fixed_at: string;
  fee_bps_per_side: number;
  spread_bps_round_trip: number;
  slippage_bps_round_trip: number;
  liquidity_impact_bps_round_trip: number;
  max_participation_bps: number;
  minimum_daily_notional_minor_units: number;
}>;

export type NewsResearchFeatureAvailability = Readonly<{
  observation_id: string;
  partition: NewsResearchPartitionName;
  source_provenance_sha256: string;
  temporal_replay_sha256: string;
  feature_available_at: string;
  transformed_at: string;
  decision_time: string;
}>;

export type NewsResearchResult = Readonly<{
  partition: NewsResearchEvaluationPartition;
  variant: NewsResearchVariant;
  variant_spec_sha256: string;
  cost_model_sha256: string;
  dataset_sha256: string;
  result_sha256: string;
  evaluated_at: string;
  sample_count: number;
  round_trip_count: number;
  gross_return_bps: number;
  assessed_cost_bps: number;
  net_return_bps: number;
}>;

export type NewsContextResearchValueEvidence = Readonly<{
  contract_id: string;
  contract_version: number;
  frozen_at: string;
  claim: Readonly<{
    scope: "bounded_comparative_evidence_only";
    performance_claim: "none";
    authority_effect: "none";
  }>;
  provenance: Readonly<{
    code_sha256: string;
    dataset_manifest_sha256: string;
    feature_source_sha256: string;
    frozen_protocol_sha256: string;
  }>;
  protocol: Readonly<{
    selection_partition: "validation";
    holdout_used_for_selection: false;
    minimum_sample_count: number;
    label_horizon_ms: number;
    feature_dependency_horizon_ms: number;
    purge_ms: number;
    embargo_ms: number;
    baseline_spec_sha256: string;
    feature_spec_sha256: string;
    lagged_spec_sha256: string;
    lag_ms: number;
    shuffled_spec_sha256: string;
    shuffle_seed: number;
    placebo_spec_sha256: string;
    placebo_seed: number;
  }>;
  costs: NewsResearchCostAssumptions;
  partitions: readonly NewsResearchPartition[];
  feature_availability: readonly NewsResearchFeatureAvailability[];
  holdout_opened_at: string;
  results: readonly NewsResearchResult[];
}>;

export type NewsResearchPartitionComparison = Readonly<{
  partition: NewsResearchEvaluationPartition;
  baseline_plus_feature_net_bps: number;
  strongest_comparator_net_bps: number;
  incremental_margin_bps: number;
}>;

export type NewsContextResearchValueDecision = Readonly<{
  contract_id: typeof NEWS_CONTEXT_RESEARCH_VALUE_CONTRACT_ID;
  status: "eligible_for_bounded_review" | "rejected";
  reasons: readonly NewsResearchValueRejectionReason[];
  comparisons: readonly NewsResearchPartitionComparison[];
  performance_claim: "none";
  authority_effect: "none";
}>;

type UnknownRecord = Record<string, unknown>;

const SHA256 = /^[0-9a-f]{64}$/;
const ISO_TIMESTAMP = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(Z|[+-](\d{2}):(\d{2}))$/;
const PARTITIONS: readonly NewsResearchPartitionName[] = ["train", "validation", "holdout"];
const EVALUATION_PARTITIONS: readonly NewsResearchEvaluationPartition[] = ["validation", "holdout"];
const REASON_ORDER: readonly NewsResearchValueRejectionReason[] = [
  "invalid_contract_identity",
  "missing_provenance",
  "invalid_frozen_protocol",
  "invalid_partition_boundary",
  "partition_order_violation",
  "insufficient_purge_or_embargo",
  "invalid_control_specification",
  "invalid_cost_assumptions",
  "temporal_leakage",
  "holdout_selection_violation",
  "missing_control_result",
  "result_scope_mismatch",
  "insufficient_sample_count",
  "result_accounting_mismatch",
  "unsupported_performance_claim",
  "feature_not_incremental",
];

function record(value: unknown): UnknownRecord | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as UnknownRecord
    : null;
}

function nonBlank(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function sha256(value: unknown): value is string {
  return typeof value === "string" && SHA256.test(value);
}

function safeInteger(value: unknown, minimum = Number.MIN_SAFE_INTEGER): value is number {
  return Number.isSafeInteger(value) && (value as number) >= minimum;
}

function parseTimestamp(value: unknown): number | null {
  if (typeof value !== "string") return null;
  const match = value.match(ISO_TIMESTAMP);
  if (!match) return null;

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
    month < 1 || month > 12 || day < 1 || day > daysInMonth[month - 1] ||
    hour > 23 || minute > 59 || second > 59 || offsetHour > 23 || offsetMinute > 59
  ) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function orderedReasons(
  reasons: ReadonlySet<NewsResearchValueRejectionReason>,
): readonly NewsResearchValueRejectionReason[] {
  return REASON_ORDER.filter((reason) => reasons.has(reason));
}

function partitionMap(
  value: unknown,
  reasons: Set<NewsResearchValueRejectionReason>,
): Map<NewsResearchPartitionName, { raw: UnknownRecord; start: number; end: number }> {
  const partitions = new Map<NewsResearchPartitionName, { raw: UnknownRecord; start: number; end: number }>();
  if (!Array.isArray(value)) {
    reasons.add("invalid_partition_boundary");
    return partitions;
  }

  for (const item of value) {
    const raw = record(item);
    const name = raw?.name;
    if (!raw || !PARTITIONS.includes(name as NewsResearchPartitionName)) {
      reasons.add("invalid_partition_boundary");
      continue;
    }
    if (partitions.has(name as NewsResearchPartitionName)) {
      reasons.add("invalid_partition_boundary");
      continue;
    }
    const start = parseTimestamp(raw.start);
    const end = parseTimestamp(raw.end);
    if (start === null || end === null || start >= end || !sha256(raw.dataset_sha256)) {
      reasons.add(start === null || end === null || start >= end
        ? "invalid_partition_boundary"
        : "missing_provenance");
      continue;
    }
    partitions.set(name as NewsResearchPartitionName, { raw, start, end });
  }

  if (partitions.size !== PARTITIONS.length) reasons.add("invalid_partition_boundary");
  return partitions;
}

function validatePartitionSeparation(
  partitions: ReadonlyMap<NewsResearchPartitionName, { raw: UnknownRecord; start: number; end: number }>,
  protocol: UnknownRecord | null,
  reasons: Set<NewsResearchValueRejectionReason>,
): void {
  const train = partitions.get("train");
  const validation = partitions.get("validation");
  const holdout = partitions.get("holdout");
  if (!train || !validation || !holdout) return;

  const labelHorizon = protocol?.label_horizon_ms;
  const dependencyHorizon = protocol?.feature_dependency_horizon_ms;
  const purge = protocol?.purge_ms;
  const embargo = protocol?.embargo_ms;
  if (
    !safeInteger(labelHorizon, 0) || !safeInteger(dependencyHorizon, 0) ||
    !safeInteger(purge, 0) || !safeInteger(embargo, 0)
  ) {
    reasons.add("invalid_frozen_protocol");
    return;
  }
  const overlapRisk = labelHorizon > 0 || dependencyHorizon > 0;
  if (overlapRisk && (purge === 0 || embargo === 0)) {
    reasons.add("insufficient_purge_or_embargo");
  }

  if (!(train.end < validation.start && validation.end < holdout.start)) {
    reasons.add("partition_order_violation");
    return;
  }
  const requiredSeparation = labelHorizon + dependencyHorizon + purge + embargo;
  if (!Number.isSafeInteger(requiredSeparation)) {
    reasons.add("invalid_frozen_protocol");
    return;
  }
  if (
    validation.start - train.end < requiredSeparation ||
    holdout.start - validation.end < requiredSeparation
  ) {
    reasons.add("insufficient_purge_or_embargo");
  }
}

function validateProtocol(
  protocol: UnknownRecord | null,
  reasons: Set<NewsResearchValueRejectionReason>,
): Map<NewsResearchVariant, string> {
  const specs = new Map<NewsResearchVariant, string>();
  if (!protocol) {
    reasons.add("invalid_frozen_protocol");
    return specs;
  }
  if (protocol.selection_partition !== "validation" || protocol.holdout_used_for_selection !== false) {
    reasons.add("holdout_selection_violation");
  }
  if (!safeInteger(protocol.minimum_sample_count, 1)) {
    reasons.add("invalid_frozen_protocol");
  }
  const specFields: readonly [NewsResearchVariant, string][] = [
    ["baseline", "baseline_spec_sha256"],
    ["baseline_plus_feature", "feature_spec_sha256"],
    ["lagged", "lagged_spec_sha256"],
    ["shuffled", "shuffled_spec_sha256"],
    ["placebo", "placebo_spec_sha256"],
  ];
  for (const [variant, field] of specFields) {
    const value = protocol[field];
    if (!sha256(value)) reasons.add("missing_provenance");
    else specs.set(variant, value);
  }
  if (specs.size === specFields.length && new Set(specs.values()).size !== specFields.length) {
    reasons.add("invalid_control_specification");
  }
  if (
    !safeInteger(protocol.lag_ms, 1) ||
    !safeInteger(protocol.shuffle_seed, 0) ||
    !safeInteger(protocol.placebo_seed, 0) ||
    protocol.shuffle_seed === protocol.placebo_seed
  ) {
    reasons.add("invalid_control_specification");
  }
  if (
    safeInteger(protocol.feature_dependency_horizon_ms, 0) &&
    safeInteger(protocol.lag_ms, 1) &&
    protocol.lag_ms < protocol.feature_dependency_horizon_ms
  ) {
    reasons.add("invalid_control_specification");
  }
  return specs;
}

function validateCosts(
  value: UnknownRecord | null,
  frozenAt: number | null,
  reasons: Set<NewsResearchValueRejectionReason>,
): { modelSha: string; roundTripCostBps: number } | null {
  if (!value || !sha256(value.model_sha256) || !sha256(value.provenance_sha256)) {
    reasons.add("missing_provenance");
    return null;
  }
  const fixedAt = parseTimestamp(value.fixed_at);
  const integerFields = [
    value.fee_bps_per_side,
    value.spread_bps_round_trip,
    value.slippage_bps_round_trip,
    value.liquidity_impact_bps_round_trip,
    value.max_participation_bps,
    value.minimum_daily_notional_minor_units,
  ];
  if (
    fixedAt === null || frozenAt === null || fixedAt > frozenAt ||
    !integerFields.every((item) => safeInteger(item, 0)) ||
    !safeInteger(value.fee_bps_per_side, 1) ||
    !safeInteger(value.spread_bps_round_trip, 1) ||
    !safeInteger(value.slippage_bps_round_trip, 1) ||
    !safeInteger(value.max_participation_bps, 1) || value.max_participation_bps > 1_000 ||
    !safeInteger(value.minimum_daily_notional_minor_units, 1)
  ) {
    reasons.add("invalid_cost_assumptions");
    return null;
  }
  const roundTripCostBps =
    (value.fee_bps_per_side as number) * 2 +
    (value.spread_bps_round_trip as number) +
    (value.slippage_bps_round_trip as number) +
    (value.liquidity_impact_bps_round_trip as number);
  if (!Number.isSafeInteger(roundTripCostBps) || roundTripCostBps <= 0) {
    reasons.add("invalid_cost_assumptions");
    return null;
  }
  return { modelSha: value.model_sha256 as string, roundTripCostBps };
}

function validateFeatureAvailability(
  value: unknown,
  partitions: ReadonlyMap<NewsResearchPartitionName, { raw: UnknownRecord; start: number; end: number }>,
  reasons: Set<NewsResearchValueRejectionReason>,
): void {
  if (!Array.isArray(value)) {
    reasons.add("temporal_leakage");
    return;
  }
  const covered = new Set<NewsResearchPartitionName>();
  const identities = new Set<string>();
  for (const item of value) {
    const raw = record(item);
    const partitionName = raw?.partition;
    const partition = partitions.get(partitionName as NewsResearchPartitionName);
    if (!raw || !partition || !nonBlank(raw.observation_id)) {
      reasons.add("temporal_leakage");
      continue;
    }
    if (identities.has(raw.observation_id)) {
      reasons.add("temporal_leakage");
    }
    identities.add(raw.observation_id);
    covered.add(partitionName as NewsResearchPartitionName);
    if (
      !sha256(raw.source_provenance_sha256) ||
      !sha256(raw.temporal_replay_sha256)
    ) {
      reasons.add("missing_provenance");
    }

    const available = parseTimestamp(raw.feature_available_at);
    const transformed = parseTimestamp(raw.transformed_at);
    const decision = parseTimestamp(raw.decision_time);
    if (
      available === null || transformed === null || decision === null ||
      available > transformed || transformed > decision ||
      decision < partition.start || decision >= partition.end
    ) {
      reasons.add("temporal_leakage");
    }
  }
  if (PARTITIONS.some((name) => !covered.has(name))) reasons.add("temporal_leakage");
}

function validateResults(
  value: unknown,
  partitions: ReadonlyMap<NewsResearchPartitionName, { raw: UnknownRecord; start: number; end: number }>,
  specs: ReadonlyMap<NewsResearchVariant, string>,
  costs: { modelSha: string; roundTripCostBps: number } | null,
  minimumSampleCount: unknown,
  frozenAt: number | null,
  holdoutOpenedAt: number | null,
  reasons: Set<NewsResearchValueRejectionReason>,
): readonly NewsResearchPartitionComparison[] {
  const results = new Map<string, UnknownRecord>();
  const resultHashes = new Set<string>();
  if (!Array.isArray(value)) {
    reasons.add("missing_control_result");
    return [];
  }

  for (const item of value) {
    const raw = record(item);
    const partitionName = raw?.partition;
    const variant = raw?.variant;
    if (
      !raw || !EVALUATION_PARTITIONS.includes(partitionName as NewsResearchEvaluationPartition) ||
      !NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS.includes(variant as NewsResearchVariant)
    ) {
      reasons.add("result_scope_mismatch");
      continue;
    }
    const key = `${partitionName}:${variant}`;
    if (results.has(key)) {
      reasons.add("result_scope_mismatch");
      continue;
    }
    results.set(key, raw);

    if (sha256(raw.result_sha256)) {
      if (resultHashes.has(raw.result_sha256)) reasons.add("result_scope_mismatch");
      resultHashes.add(raw.result_sha256);
    }

    const partition = partitions.get(partitionName as NewsResearchPartitionName);
    if (
      !partition || raw.dataset_sha256 !== partition.raw.dataset_sha256 ||
      raw.variant_spec_sha256 !== specs.get(variant as NewsResearchVariant) ||
      raw.cost_model_sha256 !== costs?.modelSha ||
      !sha256(raw.result_sha256)
    ) {
      reasons.add("result_scope_mismatch");
    }
    const evaluatedAt = parseTimestamp(raw.evaluated_at);
    if (
      evaluatedAt === null || frozenAt === null || evaluatedAt < frozenAt ||
      (partition !== undefined && evaluatedAt < partition.end)
    ) {
      reasons.add("result_scope_mismatch");
    } else if (
      holdoutOpenedAt === null ||
      (partitionName === "validation" && evaluatedAt >= holdoutOpenedAt) ||
      (partitionName === "holdout" && evaluatedAt < holdoutOpenedAt)
    ) {
      reasons.add("holdout_selection_violation");
    }

    if (
      !safeInteger(raw.sample_count, 1) ||
      (safeInteger(minimumSampleCount, 1) && raw.sample_count < minimumSampleCount)
    ) {
      reasons.add("insufficient_sample_count");
    }
    if (
      !safeInteger(raw.round_trip_count, 1) ||
      !safeInteger(raw.gross_return_bps) || !safeInteger(raw.assessed_cost_bps, 0) ||
      !safeInteger(raw.net_return_bps) || !costs
    ) {
      reasons.add("result_accounting_mismatch");
      continue;
    }
    const expectedCost = raw.round_trip_count * costs.roundTripCostBps;
    if (
      !Number.isSafeInteger(expectedCost) || raw.assessed_cost_bps !== expectedCost ||
      raw.net_return_bps !== raw.gross_return_bps - raw.assessed_cost_bps
    ) {
      reasons.add("result_accounting_mismatch");
    }
  }

  const comparisons: NewsResearchPartitionComparison[] = [];
  for (const partitionName of EVALUATION_PARTITIONS) {
    const required = NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS.map(
      (variant) => results.get(`${partitionName}:${variant}`),
    );
    if (required.some((item) => item === undefined)) {
      reasons.add("missing_control_result");
      continue;
    }
    const resolved = required as UnknownRecord[];
    if (new Set(resolved.map((item) => item.sample_count)).size !== 1) {
      reasons.add("result_scope_mismatch");
    }
    if (!resolved.every((item) => safeInteger(item.net_return_bps))) continue;
    const byVariant = new Map(
      NEWS_CONTEXT_RESEARCH_VALUE_VARIANTS.map((variant, index) => [variant, resolved[index]]),
    );
    const feature = byVariant.get("baseline_plus_feature")!.net_return_bps as number;
    const comparators = ["baseline", "lagged", "shuffled", "placebo"] as const;
    const strongest = Math.max(
      ...comparators.map((variant) => byVariant.get(variant)!.net_return_bps as number),
    );
    const incremental = feature - strongest;
    if (!Number.isSafeInteger(incremental)) {
      reasons.add("result_accounting_mismatch");
      continue;
    }
    comparisons.push({
      partition: partitionName,
      baseline_plus_feature_net_bps: feature,
      strongest_comparator_net_bps: strongest,
      incremental_margin_bps: incremental,
    });
    if (incremental <= 0) reasons.add("feature_not_incremental");
  }
  return comparisons;
}

export function evaluateNewsContextResearchValue(
  evidence: unknown,
): NewsContextResearchValueDecision {
  const reasons = new Set<NewsResearchValueRejectionReason>();
  const root = record(evidence);
  if (!root) reasons.add("invalid_contract_identity");

  if (
    root?.contract_id !== NEWS_CONTEXT_RESEARCH_VALUE_CONTRACT_ID ||
    root?.contract_version !== 1
  ) {
    reasons.add("invalid_contract_identity");
  }
  const claim = record(root?.claim);
  if (
    claim?.scope !== "bounded_comparative_evidence_only" ||
    claim?.performance_claim !== "none" || claim?.authority_effect !== "none"
  ) {
    reasons.add("unsupported_performance_claim");
  }
  const provenance = record(root?.provenance);
  if (
    !provenance || !sha256(provenance.code_sha256) ||
    !sha256(provenance.dataset_manifest_sha256) || !sha256(provenance.feature_source_sha256) ||
    !sha256(provenance.frozen_protocol_sha256)
  ) {
    reasons.add("missing_provenance");
  }

  const frozenAt = parseTimestamp(root?.frozen_at);
  if (frozenAt === null) reasons.add("invalid_frozen_protocol");
  const protocol = record(root?.protocol);
  const specs = validateProtocol(protocol, reasons);
  const partitions = partitionMap(root?.partitions, reasons);
  validatePartitionSeparation(partitions, protocol, reasons);
  const costs = validateCosts(record(root?.costs), frozenAt, reasons);
  validateFeatureAvailability(root?.feature_availability, partitions, reasons);

  const holdoutOpenedAt = parseTimestamp(root?.holdout_opened_at);
  const holdoutPartition = partitions.get("holdout");
  if (
    holdoutOpenedAt === null || frozenAt === null || holdoutOpenedAt < frozenAt ||
    (holdoutPartition !== undefined && holdoutOpenedAt < holdoutPartition.end)
  ) {
    reasons.add("holdout_selection_violation");
  }
  const comparisons = validateResults(
    root?.results,
    partitions,
    specs,
    costs,
    protocol?.minimum_sample_count,
    frozenAt,
    holdoutOpenedAt,
    reasons,
  );

  const ordered = orderedReasons(reasons);
  return {
    contract_id: NEWS_CONTEXT_RESEARCH_VALUE_CONTRACT_ID,
    status: ordered.length === 0 ? "eligible_for_bounded_review" : "rejected",
    reasons: ordered,
    comparisons,
    performance_claim: "none",
    authority_effect: "none",
  };
}
