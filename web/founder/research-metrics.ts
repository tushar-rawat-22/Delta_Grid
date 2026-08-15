export type ResearchBar = {
  observed_at: string;
  close: number;
};

export type ResearchMetrics = {
  latest: number | null;
  return_1d: number | null;
  return_7d: number | null;
  return_30d: number | null;
  realized_volatility: number | null;
  maximum_drawdown: number | null;
  distance_from_high: number | null;
  observation_count: number;
  window: string;
};

export type ComparisonPoint = {
  observed_at: string;
  normalized: Record<string, number>;
};

export function annualizationPeriods(
  assetClass: unknown,
  interval: unknown,
): number {
  const asset = String(assetClass);
  const cadence = String(interval ?? "DAY");

  if (cadence === "WEEK") return 52;

  if (cadence === "HOUR") {
    return asset === "CRYPTO"
      ? 365 * 24
      : 252 * 6.5;
  }

  return asset === "CRYPTO" ? 365 : 252;
}

export function calendarWindow(
  bars: ResearchBar[],
  days: number,
  requireFullHorizon = false,
): ResearchBar[] {
  if (!Number.isFinite(days) || days <= 0) {
    return [];
  }

  const clean = bars
    .filter(
      (bar) =>
        Number.isFinite(bar.close) &&
        bar.close > 0 &&
        !Number.isNaN(
          Date.parse(bar.observed_at),
        ),
    )
    .toSorted((left, right) =>
      left.observed_at.localeCompare(
        right.observed_at,
      ),
    );

  const latest = clean.at(-1);
  if (!latest) return [];

  const cutoff =
    Date.parse(latest.observed_at) -
    days * 86_400_000;

  let anchorIndex = -1;

  for (
    let index = 0;
    index < clean.length;
    index += 1
  ) {
    if (
      Date.parse(clean[index].observed_at) <=
      cutoff
    ) {
      anchorIndex = index;
    } else {
      break;
    }
  }

  if (anchorIndex >= 0) {
    return clean.slice(anchorIndex);
  }

  return requireFullHorizon
    ? []
    : clean;
}

export function calculateMetrics(bars: ResearchBar[], annualization = 252): ResearchMetrics {
  const clean = bars
    .filter((bar) => Number.isFinite(bar.close) && bar.close > 0 && !Number.isNaN(Date.parse(bar.observed_at)))
    .toSorted((left, right) => left.observed_at.localeCompare(right.observed_at));
  const closes = clean.map((bar) => bar.close);
  const latest = closes.at(-1) ?? null;
  const returns = closes.slice(1).map((close, index) => Math.log(close / closes[index]));
  const volatility = returns.length > 1 ? standardDeviation(returns) * Math.sqrt(annualization) : null;
  let peak = closes[0] ?? 0;
  let maxDrawdown = 0;
  for (const close of closes) {
    peak = Math.max(peak, close);
    if (peak > 0) maxDrawdown = Math.min(maxDrawdown, close / peak - 1);
  }
  const high = closes.length ? Math.max(...closes) : null;
  return {
    latest,
    return_1d: horizonReturn(clean, 1),
    return_7d: horizonReturn(clean, 7),
    return_30d: horizonReturn(clean, 30),
    realized_volatility: volatility,
    maximum_drawdown: closes.length ? maxDrawdown : null,
    distance_from_high: latest !== null && high ? latest / high - 1 : null,
    observation_count: clean.length,
    window: clean.length > 1 ? `${clean[0].observed_at}/${clean.at(-1)?.observed_at ?? clean[0].observed_at}` : "INSUFFICIENT_DATA",
  };
}

export function compareSeries(series: Record<string, ResearchBar[]>): {
  points: ComparisonPoint[];
  correlations: Record<string, number | null>;
  beta_to_first: Record<string, number | null>;
} {
  const maps = Object.fromEntries(Object.entries(series).map(([id, bars]) => [
    id,
    new Map(bars.filter((bar) => Number.isFinite(bar.close) && bar.close > 0).map((bar) => [bar.observed_at, bar.close])),
  ]));
  const ids = Object.keys(maps);
  const common = ids.length
    ? [...maps[ids[0]].keys()].filter((time) => ids.every((id) => maps[id].has(time))).toSorted()
    : [];
  const bases = Object.fromEntries(ids.map((id) => [id, maps[id].get(common[0] ?? "") ?? 0]));
  const points = common.map((observedAt) => ({
    observed_at: observedAt,
    normalized: Object.fromEntries(ids.map((id) => [id, ((maps[id].get(observedAt) ?? 0) / bases[id]) * 100])),
  }));
  const returnSeries = Object.fromEntries(ids.map((id) => {
    const values = common.map((time) => maps[id].get(time) ?? 0);
    return [id, values.slice(1).map((value, index) => Math.log(value / values[index]))];
  }));
  const first = ids[0];
  return {
    points,
    correlations: Object.fromEntries(ids.map((id) => [id, first ? correlation(returnSeries[first], returnSeries[id]) : null])),
    beta_to_first: Object.fromEntries(ids.map((id) => [id, first ? beta(returnSeries[id], returnSeries[first]) : null])),
  };
}

function horizonReturn(values: ResearchBar[], days: number): number | null {
  if (values.length < 2) return null;

  const latest = values.at(-1);
  if (!latest) return null;

  const cutoff = Date.parse(latest.observed_at) - days * 86_400_000;
  let anchor: ResearchBar | null = null;

  for (const value of values) {
    if (Date.parse(value.observed_at) <= cutoff) anchor = value;
    else break;
  }

  return anchor ? latest.close / anchor.close - 1 : null;
}

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function standardDeviation(values: number[]): number {
  const average = mean(values);
  return Math.sqrt(values.reduce((sum, value) => sum + (value - average) ** 2, 0) / (values.length - 1));
}

function covariance(left: number[], right: number[]): number | null {
  if (left.length !== right.length || left.length < 2) return null;
  const leftMean = mean(left);
  const rightMean = mean(right);
  return left.reduce((sum, value, index) => sum + (value - leftMean) * (right[index] - rightMean), 0) / (left.length - 1);
}

function correlation(left: number[], right: number[]): number | null {
  const cov = covariance(left, right);
  if (cov === null) return null;
  const denominator = standardDeviation(left) * standardDeviation(right);
  return denominator === 0 ? null : cov / denominator;
}

function beta(dependent: number[], benchmark: number[]): number | null {
  const cov = covariance(dependent, benchmark);
  if (cov === null || benchmark.length < 2) return null;
  const variance = standardDeviation(benchmark) ** 2;
  return variance === 0 ? null : cov / variance;
}
