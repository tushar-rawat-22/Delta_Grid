export type HypothesisPriorityInput = {
  kind: string;
  instrument_id: string;
  symbol: string;
  metric: string;
  value: number | null;
  detail_code: string;
  latest_observed_at: string | null;
};

export type HypothesisSeed = {
  record_type: "THESIS";
  instrument_id: string;
  title: string;
  body: string;
  status: "DRAFT";
  confidence: null;
  tags: string[];
};

export function createHypothesisSeed(
  priority: HypothesisPriorityInput,
): HypothesisSeed {
  const kind = priority.kind
    .replaceAll("_", " ")
    .toLowerCase();

  const tag = priority.kind
    .toLowerCase()
    .replaceAll("_", "-");

  const observedValue =
    priority.value === null
      ? "UNAVAILABLE"
      : String(priority.value);

  const observedAt =
    priority.latest_observed_at ??
    "UNAVAILABLE";

  return {
    record_type: "THESIS",
    instrument_id:
      priority.instrument_id,
    title:
      `${priority.symbol}: investigate ${kind}`,
    status: "DRAFT",
    confidence: null,
    tags: [
      "intelligence",
      "hypothesis-draft",
      tag,
    ],
    body: [
      "OBSERVATION",
      `Priority: ${priority.kind}`,
      `Metric: ${priority.metric}`,
      `Observed value: ${observedValue}`,
      `Observed at: ${observedAt}`,
      `Data state: ${priority.detail_code}`,
      "",
      "ECONOMIC MECHANISM",
      "[Founder: state one causal economic mechanism before testing.]",
      "",
      "FALSIFICATION CONDITION",
      "[Founder: state what observation would reject the mechanism.]",
      "",
      "DATA AND CHRONOLOGY",
      "[Founder: declare exact instruments, fields, availability rule, and time window.]",
      "",
      "TEST PLAN",
      "[Founder: declare exact transformation, benchmark/control, and evaluation method.]",
      "",
      "CANDIDATE AND PARAMETER BUDGET",
      "[Founder: declare the finite number of variants before results are inspected.]",
      "",
      "COST AND EXECUTION ASSUMPTIONS",
      "[Founder: declare costs, timing, liquidity, and implementation assumptions.]",
      "",
      "MULTIPLE-TESTING FAMILY",
      "[Founder: declare the statistical family and correction before evaluation.]",
      "",
      "SUCCESS AND FAILURE RULE",
      "[Founder: define exact pass, reject, stop, and no-rescue conditions.]",
      "",
      "NEXT REVIEW",
      "[Founder: identify the evidence dependency or review date.]",
      "",
      "PREREGISTRATION HANDOFF",
      "[System: a later compiler may hash-lock the founder-authored sections above. Exact datasets, permits, trial reservations, execution specifications, statistical programmes, protected stages, Mission 104, and trading authority remain outside this notebook record.]",
    ].join("\n"),
  };
}
