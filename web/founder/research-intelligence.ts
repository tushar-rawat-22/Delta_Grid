import {
  annualizationPeriods,
  calculateMetrics,
  calendarWindow,
  compareSeries,
  type ResearchBar,
  type ResearchMetrics,
} from "./research-metrics.ts";

export type IntelligenceInstrument = {
  instrument_id: string;
  provider_id: string;
  symbol: string;
  display_name: string;
  asset_class: string;
  status: string;
  detail_code: string;
  last_success_at: string | null;
  latest_close: number | null;
  latest_observed_at: string | null;
  latest_interval: string | null;
};

export type IntelligenceRisk = {
  realized_volatility: number | null;
  maximum_drawdown: number | null;
  observation_count: number;
  window: string;
};

export type IntelligenceMarket =
  IntelligenceInstrument & {
    metrics: ResearchMetrics;
    risk_7d: IntelligenceRisk;
    observation_age_hours: number | null;
    collection_age_hours: number | null;
  };

export type IntelligenceRelationship = {
  label: string;
  left_instrument_id: string;
  right_instrument_id: string;
  correlation: number | null;
  beta_right_to_left: number | null;
  overlap_count: number;
  window_start: string | null;
  window_end: string | null;
};

export type IntelligenceMacroChange = {
  instrument_id: string;
  symbol: string;
  display_name: string;
  provider_id: string;
  latest_value: number | null;
  previous_value: number | null;
  change: number | null;
  relative_change: number | null;
  direction: "UP" | "DOWN" | "FLAT" | "UNAVAILABLE";
  unit: string | null;
  frequency: string | null;
  observed_at: string | null;
};

export type IntelligencePriority = {
  kind:
    | "DATA_HEALTH"
    | "ONE_DAY_MOVE"
    | "SEVEN_DAY_DRAWDOWN"
    | "SEVEN_DAY_VOLATILITY";
  instrument_id: string;
  symbol: string;
  metric: string;
  value: number | null;
  status: string;
  detail_code: string;
  latest_observed_at: string | null;
  authority_effect: "NONE";
};

export type MarketIntelligenceBrief = {
  generated_at: string;
  boundary: "NON_RAB1_RESEARCH_ONLY";
  authority_effect: "NONE";
  coverage: {
    market_total: number;
    market_operational: number;
    return_1d_available: number;
    return_7d_available: number;
    return_30d_available: number;
    risk_7d_available: number;
  };
  breadth: {
    positive_1d: number;
    negative_1d: number;
    flat_1d: number;
    unavailable_1d: number;
    label:
      | "MORE_MARKETS_UP"
      | "MORE_MARKETS_DOWN"
      | "BALANCED"
      | "INSUFFICIENT_DATA";
  };
  movers: {
    top_gainers: IntelligenceMarket[];
    top_decliners: IntelligenceMarket[];
  };
  risk_pressure: {
    horizon: "TRAILING_7_CALENDAR_DAYS";
    highest_volatility: IntelligenceMarket | null;
    deepest_drawdown: IntelligenceMarket | null;
  };
  relationships: {
    horizon: "UP_TO_TRAILING_30_CALENDAR_DAYS";
    pairs: IntelligenceRelationship[];
  };
  macro_changes: IntelligenceMacroChange[];
  priorities: IntelligencePriority[];
};

type BuildBriefInput = {
  instruments: IntelligenceInstrument[];
  series: Record<string, ResearchBar[]>;
  macro: Array<Record<string, unknown>>;
  generatedAt: string;
  boundary: "NON_RAB1_RESEARCH_ONLY";
  authorityEffect: "NONE";
};

const RELATIONSHIP_PAIRS = [
  {
    label: "BTC / ETH",
    left: "CRYPTO_BTC_USD",
    right: "CRYPTO_ETH_USD",
  },
  {
    label: "SPY / QQQ",
    left: "ETF_SPY",
    right: "ETF_QQQ",
  },
  {
    label: "BTC / SPY",
    left: "CRYPTO_BTC_USD",
    right: "ETF_SPY",
  },
] as const;

export function buildMarketIntelligenceBrief(
  input: BuildBriefInput,
): MarketIntelligenceBrief {
  const {
    instruments,
    series,
    macro,
    generatedAt,
    boundary,
    authorityEffect,
  } = input;

  const markets = instruments.map((instrument) => {
    const bars =
      series[instrument.instrument_id] ?? [];

    const annualization = annualizationPeriods(
      instrument.asset_class,
      instrument.latest_interval,
    );

    const metrics = calculateMetrics(
      bars,
      annualization,
    );

    /*
     * Risk comparisons require the complete declared
     * seven-calendar-day horizon. Incomplete history
     * remains unavailable.
     */
    const riskBars = calendarWindow(
      bars,
      7,
      true,
    );

    const riskMetrics = calculateMetrics(
      riskBars,
      annualization,
    );

    return {
      ...instrument,
      metrics,
      risk_7d: {
        realized_volatility:
          riskMetrics.realized_volatility,
        maximum_drawdown:
          riskMetrics.maximum_drawdown,
        observation_count:
          riskMetrics.observation_count,
        window:
          riskMetrics.window,
      },
      observation_age_hours: ageHours(
        generatedAt,
        instrument.latest_observed_at,
      ),
      collection_age_hours: ageHours(
        generatedAt,
        instrument.last_success_at,
      ),
    };
  });

  const oneDay = markets.filter(
    (market) =>
      market.metrics.return_1d !== null,
  );

  const positive = oneDay.filter(
    (market) =>
      (market.metrics.return_1d ?? 0) > 0,
  );

  const negative = oneDay.filter(
    (market) =>
      (market.metrics.return_1d ?? 0) < 0,
  );

  const flat =
    oneDay.length -
    positive.length -
    negative.length;

  const breadthLabel:
    MarketIntelligenceBrief["breadth"]["label"] =
    oneDay.length === 0
      ? "INSUFFICIENT_DATA"
      : positive.length > negative.length
        ? "MORE_MARKETS_UP"
        : negative.length > positive.length
          ? "MORE_MARKETS_DOWN"
          : "BALANCED";

  const topGainers = positive
    .toSorted(
      (left, right) =>
        (right.metrics.return_1d ?? 0) -
        (left.metrics.return_1d ?? 0),
    )
    .slice(0, 2);

  const topDecliners = negative
    .toSorted(
      (left, right) =>
        (left.metrics.return_1d ?? 0) -
        (right.metrics.return_1d ?? 0),
    )
    .slice(0, 2);

  const highestVolatility =
    markets
      .filter(
        (market) =>
          market.risk_7d.realized_volatility !==
          null,
      )
      .toSorted(
        (left, right) =>
          (right.risk_7d.realized_volatility ?? 0) -
          (left.risk_7d.realized_volatility ?? 0),
      )[0] ?? null;

  const deepestDrawdown =
    markets
      .filter(
        (market) =>
          market.risk_7d.maximum_drawdown !==
          null,
      )
      .toSorted(
        (left, right) =>
          (left.risk_7d.maximum_drawdown ?? 0) -
          (right.risk_7d.maximum_drawdown ?? 0),
      )[0] ?? null;

  const relationships =
    RELATIONSHIP_PAIRS.map((pair) => {
      /*
       * Relationship history is explicitly "up to"
       * 30 calendar days. Partial history is allowed,
       * but only exact timestamp overlap is used.
       */
      const comparison = compareSeries({
        [pair.left]: calendarWindow(
          series[pair.left] ?? [],
          30,
        ),
        [pair.right]: calendarWindow(
          series[pair.right] ?? [],
          30,
        ),
      });

      return {
        label:
          pair.label,
        left_instrument_id:
          pair.left,
        right_instrument_id:
          pair.right,
        correlation:
          comparison.correlations[
            pair.right
          ] ?? null,
        beta_right_to_left:
          comparison.beta_to_first[
            pair.right
          ] ?? null,
        overlap_count:
          comparison.points.length,
        window_start:
          comparison.points[0]
            ?.observed_at ?? null,
        window_end:
          comparison.points.at(-1)
            ?.observed_at ?? null,
      };
    });

  const macroChanges = macro
    .map(toMacroChange)
    .toSorted((left, right) => {
      const time =
        (right.observed_at ?? "")
          .localeCompare(
            left.observed_at ?? "",
          );

      return time !== 0
        ? time
        : left.display_name.localeCompare(
            right.display_name,
          );
    });

  const priorities =
    buildPriorities(
      markets,
      oneDay,
      highestVolatility,
      deepestDrawdown,
    );

  return {
    generated_at:
      generatedAt,
    boundary,
    authority_effect:
      authorityEffect,
    coverage: {
      market_total:
        markets.length,
      market_operational:
        markets.filter(
          (market) =>
            market.status === "OPERATIONAL",
        ).length,
      return_1d_available:
        markets.filter(
          (market) =>
            market.metrics.return_1d !== null,
        ).length,
      return_7d_available:
        markets.filter(
          (market) =>
            market.metrics.return_7d !== null,
        ).length,
      return_30d_available:
        markets.filter(
          (market) =>
            market.metrics.return_30d !== null,
        ).length,
      risk_7d_available:
        markets.filter(
          (market) =>
            market.risk_7d
              .realized_volatility !== null,
        ).length,
    },
    breadth: {
      positive_1d:
        positive.length,
      negative_1d:
        negative.length,
      flat_1d:
        flat,
      unavailable_1d:
        markets.length - oneDay.length,
      label:
        breadthLabel,
    },
    movers: {
      top_gainers:
        topGainers,
      top_decliners:
        topDecliners,
    },
    risk_pressure: {
      horizon:
        "TRAILING_7_CALENDAR_DAYS",
      highest_volatility:
        highestVolatility,
      deepest_drawdown:
        deepestDrawdown,
    },
    relationships: {
      horizon:
        "UP_TO_TRAILING_30_CALENDAR_DAYS",
      pairs:
        relationships,
    },
    macro_changes:
      macroChanges,
    priorities,
  };
}

function buildPriorities(
  markets: IntelligenceMarket[],
  oneDay: IntelligenceMarket[],
  highestVolatility: IntelligenceMarket | null,
  deepestDrawdown: IntelligenceMarket | null,
): IntelligencePriority[] {
  const output: IntelligencePriority[] = [];
  const used = new Set<string>();

  const add = (
    kind: IntelligencePriority["kind"],
    market: IntelligenceMarket | null,
    metric: string,
    value: number | null,
  ): void => {
    if (
      !market ||
      used.has(market.instrument_id)
    ) {
      return;
    }

    used.add(market.instrument_id);

    output.push({
      kind,
      instrument_id:
        market.instrument_id,
      symbol:
        market.symbol,
      metric,
      value,
      status:
        market.status,
      detail_code:
        market.detail_code,
      latest_observed_at:
        market.latest_observed_at,
      authority_effect:
        "NONE",
    });
  };

  const healthCandidate =
    markets
      .filter(
        (market) =>
          market.status !== "OPERATIONAL",
      )
      .toSorted(
        (left, right) =>
          statusRank(left.status) -
          statusRank(right.status),
      )[0] ?? null;

  add(
    "DATA_HEALTH",
    healthCandidate,
    "provider_status",
    null,
  );

  const largestMove =
    oneDay
      .toSorted(
        (left, right) =>
          Math.abs(
            right.metrics.return_1d ?? 0,
          ) -
          Math.abs(
            left.metrics.return_1d ?? 0,
          ),
      )[0] ?? null;

  add(
    "ONE_DAY_MOVE",
    largestMove,
    "return_1d",
    largestMove?.metrics.return_1d ??
      null,
  );

  add(
    "SEVEN_DAY_DRAWDOWN",
    deepestDrawdown,
    "maximum_drawdown_7d",
    deepestDrawdown?.risk_7d
      .maximum_drawdown ?? null,
  );

  add(
    "SEVEN_DAY_VOLATILITY",
    highestVolatility,
    "realized_volatility_7d",
    highestVolatility?.risk_7d
      .realized_volatility ?? null,
  );

  for (
    const market of oneDay.toSorted(
      (left, right) =>
        Math.abs(
          right.metrics.return_1d ?? 0,
        ) -
        Math.abs(
          left.metrics.return_1d ?? 0,
        ),
    )
  ) {
    if (output.length >= 4) break;

    add(
      "ONE_DAY_MOVE",
      market,
      "return_1d",
      market.metrics.return_1d,
    );
  }

  return output.slice(0, 4);
}

function toMacroChange(
  item: Record<string, unknown>,
): IntelligenceMacroChange {
  const latest =
    finiteNumber(item.latest_value);

  const previous =
    finiteNumber(item.previous_value);

  const change =
    latest !== null &&
    previous !== null
      ? latest - previous
      : null;

  const relativeChange =
    change !== null &&
    previous !== null &&
    previous !== 0
      ? change / Math.abs(previous)
      : null;

  return {
    instrument_id:
      textValue(item.instrument_id),
    symbol:
      textValue(item.symbol),
    display_name:
      textValue(item.display_name),
    provider_id:
      textValue(item.provider_id),
    latest_value:
      latest,
    previous_value:
      previous,
    change,
    relative_change:
      relativeChange,
    direction:
      change === null
        ? "UNAVAILABLE"
        : change > 0
          ? "UP"
          : change < 0
            ? "DOWN"
            : "FLAT",
    unit:
      nullableText(item.unit),
    frequency:
      nullableText(item.frequency),
    observed_at:
      nullableText(item.observed_at),
  };
}

function ageHours(
  now: string,
  value: string | null,
): number | null {
  if (!value) return null;

  const nowMs = Date.parse(now);
  const valueMs = Date.parse(value);

  if (
    !Number.isFinite(nowMs) ||
    !Number.isFinite(valueMs)
  ) {
    return null;
  }

  return (nowMs - valueMs) / 3_600_000;
}

function finiteNumber(
  value: unknown,
): number | null {
  return typeof value === "number" &&
    Number.isFinite(value)
    ? value
    : null;
}

function textValue(
  value: unknown,
): string {
  return typeof value === "string"
    ? value
    : "";
}

function nullableText(
  value: unknown,
): string | null {
  return typeof value === "string"
    ? value
    : null;
}

function statusRank(
  status: string,
): number {
  if (status === "FAILED") return 0;
  if (status === "DEGRADED") return 1;
  if (status === "PENDING") return 2;
  return 3;
}
