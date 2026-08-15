import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

type View = "cockpit" | "brief" | "markets" | "compare" | "macro" | "notebook" | "health";
type Instrument = {
  instrument_id: string;
  provider_id: string;
  symbol: string;
  display_name: string;
  asset_class: string;
  rights_classification: string;
  status: string;
  detail_code: string;
  last_success_at: string | null;
  latest_close: number | null;
  latest_observed_at: string | null;
  latest_interval: string | null;
};
type Watchlist = { watchlist_id: string; name: string; revision: number; items: string[] };
type ResearchRecord = {
  record_id: string;
  record_type: string;
  instrument_id: string | null;
  title: string;
  body: string;
  status: string;
  confidence: number | null;
  tags_json: string;
  source_url: string | null;
  source_published_at: string | null;
  source_accessed_at: string | null;
  due_at: string | null;
  revision: number;
  updated_at: string;
};
type MacroPoint = {
  instrument_id: string;
  symbol: string;
  display_name: string;
  provider_id: string;
  rights_classification: string;
  status: string;
  detail_code: string;
  last_success_at: string | null;
  latest_value: number | null;
  previous_value: number | null;
  unit: string | null;
  frequency: string | null;
  observed_at: string | null;
};
type ProviderHealth = {
  provider_id: string;
  instrument_id: string;
  symbol: string;
  display_name: string;
  status: string;
  last_attempt_at: string | null;
  last_success_at: string | null;
  next_due_at: string;
  detail_code: string;
  quota_state: string;
  rights_classification: string;
};
type BriefMetrics = {
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

type BriefMarket = Instrument & {
  metrics: BriefMetrics;
  risk_7d: {
    realized_volatility: number | null;
    maximum_drawdown: number | null;
    observation_count: number;
    window: string;
  };
  observation_age_hours: number | null;
  collection_age_hours: number | null;
};

type BriefRelationship = {
  label: string;
  left_instrument_id: string;
  right_instrument_id: string;
  correlation: number | null;
  beta_right_to_left: number | null;
  overlap_count: number;
  window_start: string | null;
  window_end: string | null;
};

type BriefMacroChange = {
  instrument_id: string;
  symbol: string;
  display_name: string;
  provider_id: string;
  latest_value: number | null;
  previous_value: number | null;
  change: number | null;
  relative_change: number | null;
  direction: string;
  unit: string | null;
  frequency: string | null;
  observed_at: string | null;
};

type BriefPriority = {
  kind: string;
  instrument_id: string;
  symbol: string;
  metric: string;
  value: number | null;
  status: string;
  detail_code: string;
  latest_observed_at: string | null;
  authority_effect: "NONE";
};

type MarketIntelligenceBrief = {
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
    label: string;
  };
  movers: {
    top_gainers: BriefMarket[];
    top_decliners: BriefMarket[];
  };
  risk_pressure: {
    horizon: string;
    highest_volatility: BriefMarket | null;
    deepest_drawdown: BriefMarket | null;
  };
  relationships: {
    horizon: string;
    pairs: BriefRelationship[];
  };
  macro_changes: BriefMacroChange[];
  priorities: BriefPriority[];
};

export type Bootstrap = {
  instruments: Instrument[];
  watchlists: Watchlist[];
  records: ResearchRecord[];
  macro: MacroPoint[];
  provider_health: ProviderHealth[];
  csrf_token: string;
  session_expires_at: string | null;
  generated_at: string;
  boundary: "NON_RAB1_RESEARCH_ONLY";
  authority_effect: "NONE";
};
export type Dossier = {
  instrument: Instrument;
  bars: Array<{ observed_at: string; close: number }>;
  metrics: Record<string, number | string | null>;
  fundamentals: Array<Record<string, string | number | null>>;
};
export type Comparison = {
  points: Array<{ observed_at: string; normalized: Record<string, number> }>;
  correlations: Record<string, number | null>;
  beta_to_first: Record<string, number | null>;
};

const NAV: Array<[View, string, string]> = [
  ["cockpit", "Cockpit", "⌂"],
  ["brief", "Intelligence", "◈"],
  ["markets", "Markets", "◫"],
  ["compare", "Compare", "⇄"],
  ["macro", "Macro", "◎"],
  ["notebook", "Notebook", "✎"],
  ["health", "Data health", "◇"],
];

const DEMO_VIEW = import.meta.env.DEV ? new URLSearchParams(window.location.search).get("demo") : null;

export function ResearchApp() {
  const [data, setData] = useState<Bootstrap | null>(DEMO_VIEW ? demoBootstrap() : null);
  const [view, setView] = useState<View>(DEMO_VIEW === "compare" ? "compare" : DEMO_VIEW === "dossier" ? "markets" : "cockpit");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!DEMO_VIEW);
  const [selectedInstrument, setSelectedInstrument] = useState<string | null>(DEMO_VIEW === "dossier" ? "EQUITY_AAPL" : null);

  const load = useCallback(async () => {
    if (DEMO_VIEW) return;
    setLoading(true);
    try {
      const next = await api<Bootstrap>("/api/research/v1/bootstrap");
      setData(next);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Research workspace unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const pending = Promise.resolve().then(load);
    void pending;
  }, [load]);

  if (loading && !data) return <LoadingScreen />;
  if (!data) return <FailureScreen message={error ?? "Research workspace unavailable"} retry={() => void load()} />;

  return (
    <div className="research-shell">
      <aside className="sidebar">
        <a className="research-brand" href="/research" aria-label="DeltaGrid Research home">
          <span className="brand-sigil">Δ</span>
          <span><strong>DeltaGrid</strong><small>Research Engine</small></span>
        </a>
        <nav className="research-nav" aria-label="Research workspace">
          {NAV.map(([id, label, icon]) => (
            <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id)}>
              <span aria-hidden="true">{icon}</span>{label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="boundary-chip">Research only</span>
          <p>NON_RAB1 · AUTHORITY NONE</p>
          <a href="/founder">Founder controls ↗</a>
        </div>
      </aside>
      <main className="workspace">
        <header className="workspace-header">
          <div>
            <p className="kicker">Private founder workspace</p>
            <h1>{NAV.find(([id]) => id === view)?.[1]}</h1>
          </div>
          <div className="header-status">
            <span className={healthClass(data.provider_health)}>● {healthLabel(data.provider_health)}</span>
            <span>Updated {relativeTime(data.generated_at)}</span>
            <button onClick={() => void load()} aria-label="Refresh workspace">↻</button>
          </div>
        </header>
        {error ? <div className="inline-alert">{error}</div> : null}
        {view === "cockpit" ? <Cockpit data={data} openInstrument={(id) => { setSelectedInstrument(id); setView("markets"); }} /> : null}
        {view === "brief" ? <IntelligencePage /> : null}
        {view === "markets" ? <Markets data={data} selected={selectedInstrument} setSelected={setSelectedInstrument} refresh={load} /> : null}
        {view === "compare" ? <Compare data={data} /> : null}
        {view === "macro" ? <Macro data={data} /> : null}
        {view === "notebook" ? <Notebook data={data} refresh={load} /> : null}
        {view === "health" ? <DataHealth data={data} /> : null}
      </main>
    </div>
  );
}

function IntelligencePage() {
  const [brief, setBrief] =
    useState<MarketIntelligenceBrief | null>(null);

  const [loadingBrief, setLoadingBrief] =
    useState(true);

  const [briefError, setBriefError] =
    useState<string | null>(null);

  const loadBrief = useCallback(
    async () => {
      setLoadingBrief(true);

      try {
        const result =
          await api<{
            brief: MarketIntelligenceBrief;
          }>(
            "/api/research/v1/brief",
          );

        setBrief(result.brief);
        setBriefError(null);
      } catch (cause) {
        setBriefError(
          cause instanceof Error
            ? cause.message
            : "Market intelligence unavailable",
        );
      } finally {
        setLoadingBrief(false);
      }
    },
    [],
  );

  useEffect(() => {
    let ignore = false;

    void api<{
      brief: MarketIntelligenceBrief;
    }>(
      "/api/research/v1/brief",
    )
      .then((result) => {
        if (ignore) return;

        setBrief(result.brief);
        setBriefError(null);
      })
      .catch((cause: unknown) => {
        if (ignore) return;

        setBriefError(
          cause instanceof Error
            ? cause.message
            : "Market intelligence unavailable",
        );
      })
      .finally(() => {
        if (!ignore) {
          setLoadingBrief(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  if (loadingBrief && !brief) {
    return <PanelSkeleton />;
  }

  if (!brief) {
    return (
      <section className="panel">
        <Empty
          text={
            briefError ??
            "Market intelligence unavailable."
          }
        />
      </section>
    );
  }

  const movers = [
    ...brief.movers.top_gainers.map(
      (market) => ({
        label: "Gainer",
        market,
      }),
    ),
    ...brief.movers.top_decliners.map(
      (market) => ({
        label: "Decliner",
        market,
      }),
    ),
  ];

  const highestVol =
    brief.risk_pressure
      .highest_volatility;

  const drawdown =
    brief.risk_pressure
      .deepest_drawdown;

  return (
    <div className="page-stack">
      <div className="brief-toolbar">
        <p>
          Deterministic observations only ·
          no forecasts or trading instructions
        </p>

        <button
          className="primary-button"
          onClick={() => void loadBrief()}
          disabled={loadingBrief}
        >
          {loadingBrief
            ? "Refreshing…"
            : "Refresh brief"}
        </button>
      </div>

      {briefError ? (
        <div className="inline-alert">
          {briefError}
        </div>
      ) : null}

      <section className="pulse-grid">
        <Metric
          label="1D coverage"
          value={`${brief.coverage.return_1d_available}/${brief.coverage.market_total}`}
          note="True elapsed-day returns"
        />

        <Metric
          label="30D coverage"
          value={`${brief.coverage.return_30d_available}/${brief.coverage.market_total}`}
          note="No observation-count shortcut"
        />

        <Metric
          label="1D breadth"
          value={`${brief.breadth.positive_1d} ↑ / ${brief.breadth.negative_1d} ↓`}
          note={brief.breadth.label
            .replaceAll("_", " ")
            .toLowerCase()}
        />

        <Metric
          label="Operational"
          value={`${brief.coverage.market_operational}/${brief.coverage.market_total}`}
          note="Price collection mappings"
        />
      </section>

      <div className="two-column">
        <section className="panel">
          <PanelHead
            eyebrow="Observed movement"
            title="Largest 1D moves"
            meta="Collected markets only"
          />

          {movers.length ? (
            <div className="brief-list">
              {movers.map(
                ({ label, market }) => (
                  <div
                    className="brief-row"
                    key={`${label}-${market.instrument_id}`}
                  >
                    <span>
                      <small>{label}</small>
                      <strong>
                        {market.symbol}
                      </strong>
                    </span>

                    <b
                      className={
                        (market.metrics
                          .return_1d ?? 0) >= 0
                          ? "positive"
                          : "negative"
                      }
                    >
                      {formatPercent(
                        market.metrics
                          .return_1d,
                      )}
                    </b>

                    <span>
                      <small>Observed</small>
                      <strong>
                        {market.latest_observed_at
                          ? relativeTime(
                              market.latest_observed_at,
                            )
                          : "Pending"}
                      </strong>
                    </span>
                  </div>
                ),
              )}
            </div>
          ) : (
            <Empty text="A complete 1D horizon has not been collected yet." />
          )}
        </section>

        <section className="panel">
          <PanelHead
            eyebrow="Risk pressure"
            title="Trailing 7-day risk"
            meta="Full calendar horizon required"
          />

          <div className="brief-risk-grid">
            <article>
              <span>
                Highest realized volatility
              </span>

              <strong>
                {highestVol?.symbol ?? "—"}
              </strong>

              <b>
                {formatPercent(
                  highestVol?.risk_7d
                    .realized_volatility ??
                    null,
                )}
              </b>

              <small>
                Annualized from a complete
                trailing seven-calendar-day
                window.
              </small>
            </article>

            <article>
              <span>
                Deepest drawdown
              </span>

              <strong>
                {drawdown?.symbol ?? "—"}
              </strong>

              <b>
                {formatPercent(
                  drawdown?.risk_7d
                    .maximum_drawdown ??
                    null,
                )}
              </b>

              <small>
                Peak-to-trough inside the
                same complete horizon.
              </small>
            </article>
          </div>
        </section>
      </div>

      <section className="panel">
        <PanelHead
          eyebrow="Cross-asset structure"
          title="Relationships"
          meta="Up to trailing 30 calendar days"
        />

        <div className="relationship-grid">
          {brief.relationships.pairs.map(
            (pair) => (
              <article
                className="relationship-card"
                key={pair.label}
              >
                <span>{pair.label}</span>

                <strong>
                  {formatDecimal(
                    pair.correlation,
                  )}
                </strong>

                <p>Return correlation</p>

                <footer>
                  <span>
                    β{" "}
                    {formatDecimal(
                      pair.beta_right_to_left,
                    )}
                  </span>

                  <span>
                    {pair.overlap_count}
                    {" "}aligned
                  </span>
                </footer>
              </article>
            ),
          )}
        </div>

        <p className="source-line">
          Only exactly matching observation
          timestamps are compared. Missing
          points are not interpolated.
        </p>
      </section>

      <section className="panel">
        <PanelHead
          eyebrow="Macro tape"
          title="Latest macro deltas"
          meta="Series-specific units"
        />

        {brief.macro_changes.length ? (
          <div className="brief-macro-grid">
            {brief.macro_changes
              .slice(0, 4)
              .map((item) => (
                <article
                  className="brief-macro-card"
                  key={item.instrument_id}
                >
                  <span>
                    {item.symbol}
                  </span>

                  <strong>
                    {formatMacro(
                      item.latest_value,
                      item.unit,
                    )}
                  </strong>

                  <b
                    className={
                      item.change === null
                        ? "muted"
                        : item.change >= 0
                          ? "positive"
                          : "negative"
                    }
                  >
                    {item.change === null
                      ? "No prior observation"
                      : `${
                          item.change >= 0
                            ? "+"
                            : ""
                        }${formatMacro(
                          item.change,
                          item.unit,
                        )}`}
                  </b>

                  <small>
                    {item.observed_at
                      ? item.observed_at
                          .slice(0, 10)
                      : "Pending"}
                  </small>
                </article>
              ))}
          </div>
        ) : (
          <Empty text="No macro observations are available." />
        )}

        <p className="source-line">
          Macro series are not ranked against
          one another because their units and
          economic meanings differ.
        </p>
      </section>

      <section className="panel">
        <PanelHead
          eyebrow="Founder attention"
          title="Research priorities"
          meta="Deterministic flags · not recommendations"
        />

        {brief.priorities.length ? (
          <div className="priority-list">
            {brief.priorities.map(
              (priority) => (
                <article
                  className="priority-item"
                  key={`${priority.kind}-${priority.instrument_id}`}
                >
                  <span>
                    {priority.kind
                      .replaceAll("_", " ")}
                  </span>

                  <strong>
                    {priority.symbol}
                  </strong>

                  <p>
                    {priority.value === null
                      ? priority.detail_code
                          .replaceAll(
                            "_",
                            " ",
                          )
                          .toLowerCase()
                      : formatPercent(
                          priority.value,
                        )}
                  </p>

                  <small>
                    {priority.metric
                      .replaceAll("_", " ")}
                  </small>
                </article>
              ),
            )}
          </div>
        ) : (
          <Empty text="No deterministic attention flag is currently available." />
        )}
      </section>

      <p className="source-line">
        Generated{" "}
        {relativeTime(
          brief.generated_at,
        )}
        {" · "}
        {brief.boundary}
        {" · authority "}
        {brief.authority_effect}.
        {" "}Observed research conditions only;
        no signal, order, allocation or RAB-1
        evidence is created.
      </p>
    </div>
  );
}

function Cockpit({ data, openInstrument }: { data: Bootstrap; openInstrument(id: string): void }) {
  const watchlist = data.watchlists[0];
  const watched = data.instruments.filter((instrument) => watchlist?.items.includes(instrument.instrument_id));
  const tasks = data.records.filter((record) => record.record_type === "TASK" && record.status !== "DONE").slice(0, 4);
  const catalysts = data.records.filter((record) => record.record_type === "CATALYST").slice(0, 4);
  const recent = data.records.slice(0, 4);
  const marketInstruments = data.instruments.filter((instrument) => ["CRYPTO", "US_EQUITY", "US_ETF"].includes(instrument.asset_class));
  const reportingMarkets = marketInstruments.filter((instrument) => instrument.latest_close !== null).length;
  const reportingMacro = data.macro.filter((instrument) => instrument.latest_value !== null).length;
  const operationalSources = new Set(data.provider_health.filter((item) => item.status === "OPERATIONAL").map((item) => item.provider_id)).size;
  const operationalMappings = data.provider_health.filter((item) => item.status === "OPERATIONAL").length;
  return (
    <div className="page-stack">
      <section className="pulse-grid">
        <Metric label="Markets reporting" value={`${reportingMarkets}/${marketInstruments.length}`} note="Price history available" />
        <Metric label="Macro reporting" value={`${reportingMacro}/${data.macro.length}`} note="Latest observation available" />
        <Metric label="Sources live" value={`${operationalSources}/5`} note="At least one successful capture" />
        <Metric label="Collection coverage" value={`${operationalMappings}/${data.provider_health.length}`} note="Per-instrument health" />
      </section>
      <section className="panel wide">
        <PanelHead eyebrow="Market pulse" title={watchlist?.name ?? "Core watchlist"} meta="Delayed, source-timestamped observations" />
        <div className="market-strip">
          {watched.map((instrument) => (
            <button key={instrument.instrument_id} className="market-tile" onClick={() => openInstrument(instrument.instrument_id)}>
              <span><strong>{instrument.symbol}</strong><small>{instrument.asset_class.replaceAll("_", " ")}</small></span>
              <b>{formatNumber(instrument.latest_close)}</b>
              <em className={instrument.status === "OPERATIONAL" ? "positive" : "muted"}>{instrument.status}</em>
              <small>{instrument.latest_observed_at ? relativeTime(instrument.latest_observed_at) : "Awaiting first capture"}</small>
            </button>
          ))}
        </div>
      </section>
      <div className="two-column">
        <section className="panel">
          <PanelHead eyebrow="Focus queue" title="Research tasks" meta="Manual work only" />
          <RecordList records={tasks} empty="No open research tasks." />
        </section>
        <section className="panel">
          <PanelHead eyebrow="Calendar" title="Catalysts" meta="Founder-authored" />
          <RecordList records={catalysts} empty="No catalysts recorded." />
        </section>
      </div>
      <section className="panel">
        <PanelHead eyebrow="Research memory" title="Recently edited" meta="Revisioned records" />
        <RecordList records={recent} empty="Start in Notebook to create the first record." />
      </section>
    </div>
  );
}

function Markets({ data, selected, setSelected, refresh }: { data: Bootstrap; selected: string | null; setSelected(id: string | null): void; refresh(): Promise<void> }) {
  const [dossier, setDossier] = useState<Dossier | null>(DEMO_VIEW ? demoDossier() : null);
  const watchlist = data.watchlists[0];
  useEffect(() => {
    if (!selected || DEMO_VIEW) return;
    let active = true;
    void api<Dossier>(`/api/research/v1/instruments/${selected}`).then((result) => {
      if (active) setDossier(result);
    });
    return () => { active = false; };
  }, [selected]);

  async function toggleWatch(instrumentId: string) {
    if (!watchlist) return;
    const next = watchlist.items.includes(instrumentId)
      ? watchlist.items.filter((id) => id !== instrumentId)
      : [...watchlist.items, instrumentId];
    await apiWrite(`/api/research/v1/watchlists/${watchlist.watchlist_id}`, data.csrf_token, "PUT", {
      name: watchlist.name, instrument_ids: next, revision: watchlist.revision,
    });
    await refresh();
  }

  if (selected) return (
    <div className="page-stack">
      <button className="back-button" onClick={() => setSelected(null)}>← All markets</button>
      {!dossier || dossier.instrument.instrument_id !== selected ? <PanelSkeleton /> : <DossierView dossier={dossier} />}
    </div>
  );

  return (
    <section className="panel market-table-panel">
      <PanelHead eyebrow="Coverage" title="Markets" meta="Raw daily equities · settled hourly crypto" />
      <div className="data-table market-table">
        <div className="table-row table-head"><span>Instrument</span><span>Asset class</span><span>Latest</span><span>Observed</span><span>Source</span><span>Watch</span></div>
        {data.instruments.map((instrument) => (
          <div className="table-row" key={instrument.instrument_id}>
            <button className="instrument-name" onClick={() => setSelected(instrument.instrument_id)}><strong>{instrument.symbol}</strong><small>{instrument.display_name}</small></button>
            <span>{instrument.asset_class.replaceAll("_", " ")}</span>
            <span>{formatNumber(instrument.latest_close)}</span>
            <span>{instrument.latest_observed_at ? relativeTime(instrument.latest_observed_at) : "Pending"}</span>
            <span><b className={`status-dot ${instrument.status.toLowerCase()}`}>{instrument.status}</b><small>{instrument.provider_id.replaceAll("_", " ")}</small></span>
            <button className="star-button" onClick={() => void toggleWatch(instrument.instrument_id)} aria-label={`Toggle ${instrument.symbol} watchlist`}>
              {watchlist?.items.includes(instrument.instrument_id) ? "★" : "☆"}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function DossierView({ dossier }: { dossier: Dossier }) {
  const metric = dossier.metrics;
  return (
    <>
      <section className="dossier-hero panel">
        <div><p className="kicker">{dossier.instrument.asset_class.replaceAll("_", " ")}</p><h2>{dossier.instrument.symbol}</h2><p>{dossier.instrument.display_name}</p></div>
        <div className="dossier-price"><strong>{formatNumber(metric.latest as number | null)}</strong><span>{dossier.instrument.status} · {dossier.instrument.provider_id.replaceAll("_", " ")}</span></div>
      </section>
      <section className="panel chart-panel">
        <PanelHead eyebrow="Price history" title="Observation series" meta={`${String(metric.window)} · ${dossier.instrument.latest_interval ?? "Pending"} · raw`} />
        <LineChart points={dossier.bars} />
      </section>
      <section className="pulse-grid dossier-metrics">
        <Metric label="1D return" value={formatPercent(metric.return_1d as number | null)} note="Close to close" />
        <Metric label="30D return" value={formatPercent(metric.return_30d as number | null)} note="Available observations" />
        <Metric label="Realized vol" value={formatPercent(metric.realized_volatility as number | null)} note="Annualized" />
        <Metric label="Maximum drawdown" value={formatPercent(metric.maximum_drawdown as number | null)} note="Displayed window" />
      </section>
      <div className="two-column">
        <section className="panel">
          <PanelHead eyebrow="Company facts" title="SEC fundamentals" meta="Filed facts · not estimates" />
          {dossier.fundamentals.length ? <div className="fact-list">{dossier.fundamentals.slice(0, 8).map((fact, index) => <div key={index}><span>{String(fact.metric_key)}</span><strong>{formatNumber(Number(fact.value))}</strong><small>{String(fact.period_end)} · {String(fact.form)}</small></div>)}</div> : <Empty text="No SEC fundamentals collected for this instrument." />}
        </section>
        <section className="panel">
          <PanelHead eyebrow="Research frame" title="Thesis checklist" meta="Founder-authored in Notebook" />
          <div className="thesis-grid"><div><span>Bull case</span><p>Record evidence and invalidation conditions.</p></div><div><span>Base case</span><p>Define the expected path and review date.</p></div><div><span>Bear case</span><p>State risks before conviction rises.</p></div></div>
        </section>
      </div>
      <p className="source-line">Source: {dossier.instrument.provider_id.replaceAll("_", " ")} · {dossier.instrument.rights_classification} · observation count {String(metric.observation_count)}</p>
    </>
  );
}

function Compare({ data }: { data: Bootstrap }) {
  const defaults = data.instruments.slice(0, 3).map((item) => item.instrument_id);
  const [selected, setSelected] = useState(defaults);
  const [comparison, setComparison] = useState<Comparison | null>(DEMO_VIEW ? demoComparison() : null);
  const [busy, setBusy] = useState(false);
  const run = useCallback(async () => {
    if (DEMO_VIEW) { setComparison(demoComparison()); return; }
    if (selected.length < 2) return;
    setBusy(true);
    try {
      const result = await apiWrite<{ comparison: Comparison }>("/api/research/v1/compare", data.csrf_token, "POST", { instrument_ids: selected });
      setComparison(result.comparison);
    } finally { setBusy(false); }
  }, [data.csrf_token, selected]);
  function toggle(id: string) {
    setSelected((current) => current.includes(id) ? current.filter((value) => value !== id) : current.length < 4 ? [...current, id] : current);
  }
  const chartPoints = comparison?.points.map((point) => ({ observed_at: point.observed_at, close: point.normalized[selected[0]] ?? 100 })) ?? [];
  return (
    <div className="page-stack">
      <section className="panel">
        <PanelHead eyebrow="Selection" title="Compare up to four markets" meta="Aligned observations only" />
        <div className="selection-grid">{data.instruments.map((instrument) => <button key={instrument.instrument_id} className={selected.includes(instrument.instrument_id) ? "selected" : ""} onClick={() => toggle(instrument.instrument_id)}><strong>{instrument.symbol}</strong><small>{instrument.asset_class.replaceAll("_", " ")}</small></button>)}</div>
        <button className="primary-button" disabled={selected.length < 2 || busy} onClick={() => void run()}>{busy ? "Comparing…" : "Run comparison"}</button>
      </section>
      <section className="panel chart-panel">
        <PanelHead eyebrow="Normalized performance" title="Indexed to 100" meta="Common observation dates" />
        {comparison?.points.length ? <LineChart points={chartPoints} /> : <Empty text="Select instruments with overlapping collected history." />}
      </section>
      <section className="compare-grid">
        {selected.map((id) => {
          const instrument = data.instruments.find((item) => item.instrument_id === id);
          return <div className="panel compact" key={id}><span className="kicker">{instrument?.symbol ?? id}</span><strong>{formatDecimal(comparison?.correlations[id] ?? null)}</strong><p>Correlation to {data.instruments.find((item) => item.instrument_id === selected[0])?.symbol ?? "benchmark"}</p><small>Beta {formatDecimal(comparison?.beta_to_first[id] ?? null)}</small></div>;
        })}
      </section>
      <p className="source-line">Calculations: log returns, sample covariance, aligned dates. Window ends at the latest common observation. Research only.</p>
    </div>
  );
}

function Macro({ data }: { data: Bootstrap }) {
  return (
    <div className="page-stack">
      <section className="macro-grid">
        {data.macro.map((item) => {
          const change = item.latest_value !== null && item.previous_value !== null ? item.latest_value - item.previous_value : null;
          return <article className="panel macro-card" key={item.instrument_id}><div><span className="kicker">{item.provider_id.replaceAll("_", " ")}</span><h2>{item.display_name}</h2></div><strong>{formatMacro(item.latest_value, item.unit)}</strong><span className={change !== null && change >= 0 ? "positive" : "negative"}>{change === null ? "No prior observation" : `${change >= 0 ? "+" : ""}${formatDecimal(change)} vs prior`}</span><footer><span>{item.frequency ?? "Pending"}</span><span>{item.observed_at ?? "Awaiting first capture"}</span></footer></article>;
        })}
      </section>
      <p className="source-line">FRED series require attribution and can contain third-party source restrictions. Treasury data comes from Fiscal Data. Every card shows its observation date rather than implying real-time freshness.</p>
    </div>
  );
}

function Notebook({ data, refresh }: { data: Bootstrap; refresh(): Promise<void> }) {
  const [filter, setFilter] = useState("ALL");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<ResearchRecord | null>(null);
  const records = useMemo(() => data.records.filter((record) => (filter === "ALL" || record.record_type === filter) && `${record.title} ${record.body} ${record.tags_json}`.toLowerCase().includes(query.toLowerCase())), [data.records, filter, query]);
  return (
    <div className="notebook-layout">
      <section className="panel notebook-index">
        <PanelHead eyebrow="Research memory" title="Notebook" meta={`${data.records.length} revisioned records`} />
        <div className="notebook-tools"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search notes, tags, evidence…" aria-label="Search notebook" /><select value={filter} onChange={(event) => setFilter(event.target.value)}><option>ALL</option>{["NOTE", "THESIS", "EVIDENCE", "JOURNAL", "CATALYST", "RISK", "TASK"].map((type) => <option key={type}>{type}</option>)}</select><button className="primary-button" onClick={() => setEditing(emptyRecord())}>New record</button></div>
        <RecordList records={records} empty="No matching research records." onSelect={setEditing} />
      </section>
      <section className="panel editor-panel">
        {editing ? <RecordEditor record={editing} data={data} saved={async () => { setEditing(null); await refresh(); }} /> : <Empty text="Select a record or create a new note, thesis, evidence item, journal entry, catalyst, risk, or task." />}
      </section>
    </div>
  );
}

function RecordEditor({ record, data, saved }: { record: ResearchRecord; data: Bootstrap; saved(): Promise<void> }) {
  const [draft, setDraft] = useState(record);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true);
    const payload = {
      record_type: draft.record_type, instrument_id: draft.instrument_id, title: draft.title,
      body: draft.body, status: draft.status, confidence: draft.confidence,
      tags: parseTags(draft.tags_json), source_url: draft.source_url,
      source_published_at: draft.source_published_at, source_accessed_at: draft.source_accessed_at,
      due_at: draft.due_at, ...(draft.record_id ? { revision: draft.revision } : {}),
    };
    try {
      await apiWrite(draft.record_id ? `/api/research/v1/records/${draft.record_id}` : "/api/research/v1/records", data.csrf_token, draft.record_id ? "PUT" : "POST", payload);
      await saved();
    } finally { setBusy(false); }
  }
  return <form className="record-editor" onSubmit={(event) => void submit(event)}><div className="form-row"><label>Type<select value={draft.record_type} onChange={(event) => setDraft({ ...draft, record_type: event.target.value })}>{["NOTE", "THESIS", "EVIDENCE", "JOURNAL", "CATALYST", "RISK", "TASK"].map((type) => <option key={type}>{type}</option>)}</select></label><label>Status<select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}>{["DRAFT", "ACTIVE", "WATCHING", "DONE", "ARCHIVED"].map((status) => <option key={status}>{status}</option>)}</select></label></div><label>Title<input required maxLength={180} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label><label>Instrument<select value={draft.instrument_id ?? ""} onChange={(event) => setDraft({ ...draft, instrument_id: event.target.value || null })}><option value="">General research</option>{data.instruments.map((instrument) => <option key={instrument.instrument_id} value={instrument.instrument_id}>{instrument.symbol} — {instrument.display_name}</option>)}</select></label><label>Research body<textarea maxLength={32768} rows={12} value={draft.body} onChange={(event) => setDraft({ ...draft, body: event.target.value })} placeholder="Evidence, reasoning, invalidation conditions, and next review…" /></label><div className="form-row"><label>Confidence<input type="number" min="0" max="100" value={draft.confidence ?? ""} onChange={(event) => setDraft({ ...draft, confidence: event.target.value ? Number(event.target.value) : null })} /></label><label>Tags<input value={parseTags(draft.tags_json).join(", ")} onChange={(event) => setDraft({ ...draft, tags_json: JSON.stringify(event.target.value.split(",").map((tag) => tag.trim()).filter(Boolean)) })} placeholder="valuation, catalyst" /></label></div><label>Source URL<input type="url" value={draft.source_url ?? ""} onChange={(event) => setDraft({ ...draft, source_url: event.target.value || null })} placeholder="https://" /></label><div className="editor-footer"><span>{draft.record_id ? `Revision ${draft.revision}` : "New revisioned record"}</span><button className="primary-button" disabled={busy}>{busy ? "Saving…" : "Save record"}</button></div></form>;
}

function DataHealth({ data }: { data: Bootstrap }) {
  return (
    <div className="page-stack">
      <section className="pulse-grid">
        <Metric label="Operational" value={String(data.provider_health.filter((item) => item.status === "OPERATIONAL").length)} note="Successful latest receipt" />
        <Metric label="Pending" value={String(data.provider_health.filter((item) => item.status === "PENDING").length)} note="Awaiting first capture" />
        <Metric label="Degraded" value={String(data.provider_health.filter((item) => item.status === "DEGRADED").length)} note="Key, quota, or freshness" />
        <Metric label="Failed" value={String(data.provider_health.filter((item) => item.status === "FAILED").length)} note="Explicit provider failure" />
      </section>
      <section className="panel">
        <PanelHead eyebrow="Provider ledger" title="Collection health" meta="No silent carry-forward" />
        <div className="data-table health-table"><div className="table-row table-head"><span>Provider / instrument</span><span>Status</span><span>Last success</span><span>Next due</span><span>Quota</span><span>Rights</span></div>{data.provider_health.map((item) => <div className="table-row" key={`${item.provider_id}-${item.instrument_id}`}><span><strong>{item.symbol}</strong><small>{item.provider_id.replaceAll("_", " ")}</small></span><span><b className={`status-dot ${item.status.toLowerCase()}`}>{item.status}</b><small>{item.detail_code.replaceAll("_", " ")}</small></span><span>{item.last_success_at ? relativeTime(item.last_success_at) : "Never"}</span><span>{item.next_due_at}</span><span>{item.quota_state.replaceAll("_", " ")}</span><span>{item.rights_classification.replaceAll("_", " ")}</span></div>)}</div>
      </section>
      <section className="panel export-panel"><div><p className="kicker">Founder custody</p><h2>Export your research</h2><p>Exports contain founder-authored records and research-only derived values. They never include M100–M103 or RAB-1 protected evidence.</p></div><div><a href="/api/research/v1/export?format=json">JSON</a><a href="/api/research/v1/export?format=csv">CSV</a><a href="/api/research/v1/export?format=markdown">Markdown</a></div></section>
    </div>
  );
}

function LineChart({ points }: { points: Array<{ observed_at: string; close: number }> }) {
  const clean = points.filter((point) => Number.isFinite(point.close));
  if (clean.length < 2) return <Empty text="Not enough collected observations for a chart." />;
  const width = 900, height = 280, pad = 20;
  const min = Math.min(...clean.map((point) => point.close));
  const max = Math.max(...clean.map((point) => point.close));
  const span = max - min || 1;
  const path = clean.map((point, index) => `${index ? "L" : "M"}${pad + index * (width - 2 * pad) / (clean.length - 1)},${height - pad - (point.close - min) * (height - 2 * pad) / span}`).join(" ");
  return <div className="line-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Price observations from ${clean[0].observed_at} to ${clean.at(-1)?.observed_at ?? clean[0].observed_at}`} preserveAspectRatio="none"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#62e6bd" stopOpacity=".3"/><stop offset="1" stopColor="#62e6bd" stopOpacity="0"/></linearGradient></defs><path className="chart-area" d={`${path} L${width - pad},${height - pad} L${pad},${height - pad} Z`} /><path className="chart-line" d={path} /></svg><div><span>{clean[0].observed_at.slice(0, 10)}</span><strong>{formatNumber(clean.at(-1)?.close ?? null)}</strong><span>{clean.at(-1)?.observed_at.slice(0, 10)}</span></div></div>;
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) { return <article className="metric-card"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>; }
function PanelHead({ eyebrow, title, meta }: { eyebrow: string; title: string; meta: string }) { return <header className="panel-head"><div><p className="kicker">{eyebrow}</p><h2>{title}</h2></div><span>{meta}</span></header>; }
function RecordList({ records, empty, onSelect }: { records: ResearchRecord[]; empty: string; onSelect?(record: ResearchRecord): void }) { if (!records.length) return <Empty text={empty} />; return <div className="record-list">{records.map((record) => <button key={record.record_id} disabled={!onSelect} onClick={() => onSelect?.(record)}><span className={`record-type type-${record.record_type.toLowerCase()}`}>{record.record_type}</span><div><strong>{record.title}</strong><p>{record.body || "No detail recorded."}</p><small>{record.status} · rev {record.revision} · {relativeTime(record.updated_at)}</small></div>{record.confidence !== null ? <b>{record.confidence}%</b> : null}</button>)}</div>; }
function Empty({ text }: { text: string }) { return <div className="empty-state"><span>◇</span><p>{text}</p></div>; }
function PanelSkeleton() { return <section className="panel skeleton"><div/><div/><div/></section>; }
function LoadingScreen() { return <div className="full-screen"><span className="brand-sigil">Δ</span><strong>Opening private research workspace</strong><p>Verifying founder access and data boundaries…</p></div>; }
function FailureScreen({ message, retry }: { message: string; retry(): void }) { return <div className="full-screen failure"><span>!</span><strong>Research workspace unavailable</strong><p>{message}</p><button onClick={retry}>Try again</button></div>; }

async function api<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", headers: { accept: "application/json" } });
  if (!response.ok) throw await apiFailure(response);
  return response.json() as Promise<T>;
}
async function apiWrite<T = Record<string, unknown>>(path: string, csrf: string, method: string, body: unknown): Promise<T> {
  const response = await fetch(path, { method, credentials: "same-origin", headers: { accept: "application/json", "content-type": "application/json", "x-deltagrid-csrf": csrf }, body: JSON.stringify(body) });
  if (!response.ok) throw await apiFailure(response);
  return response.json() as Promise<T>;
}
async function apiFailure(response: Response): Promise<Error> { try { const payload = await response.json() as { error?: string }; return new Error(payload.error?.replaceAll("_", " ") ?? `Request failed (${response.status})`); } catch { return new Error(`Request failed (${response.status})`); } }
function relativeTime(value: string): string { const delta = Date.now() - Date.parse(value); if (!Number.isFinite(delta)) return "unknown"; const minutes = Math.round(Math.abs(delta) / 60_000); if (minutes < 1) return "just now"; if (minutes < 60) return `${minutes}m ago`; const hours = Math.round(minutes / 60); if (hours < 48) return `${hours}h ago`; return `${Math.round(hours / 24)}d ago`; }
function formatNumber(value: number | null | undefined): string { if (value === null || value === undefined || !Number.isFinite(value)) return "—"; if (Math.abs(value) >= 1_000_000_000_000) return `$${(value / 1_000_000_000_000).toFixed(2)}T`; if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`; return new Intl.NumberFormat("en-US", { maximumFractionDigits: value < 10 ? 4 : 2 }).format(value); }
function formatPercent(value: number | null): string { return value === null || !Number.isFinite(value) ? "—" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(2)}%`; }
function formatDecimal(value: number | null): string { return value === null || !Number.isFinite(value) ? "—" : value.toFixed(2); }
function formatMacro(value: number | null, unit: string | null): string { if (value === null) return "—"; if (unit === "PERCENT") return `${value.toFixed(2)}%`; if (unit?.includes("USD")) return formatNumber(value); return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value); }
function healthClass(items: ProviderHealth[]): string { return items.some((item) => item.status === "FAILED") ? "health failed" : items.some((item) => item.status === "DEGRADED") ? "health degraded" : "health good"; }
function healthLabel(items: ProviderHealth[]): string { return items.some((item) => item.status === "FAILED") ? "Provider failure" : items.some((item) => item.status === "DEGRADED") ? "Data degraded" : items.some((item) => item.status === "PENDING") ? "Collection starting" : "Data healthy"; }
function parseTags(value: string): string[] { try { const parsed: unknown = JSON.parse(value); return Array.isArray(parsed) ? parsed.filter((tag): tag is string => typeof tag === "string") : []; } catch { return []; } }
function emptyRecord(): ResearchRecord { return { record_id: "", record_type: "NOTE", instrument_id: null, title: "", body: "", status: "DRAFT", confidence: null, tags_json: "[]", source_url: null, source_published_at: null, source_accessed_at: null, due_at: null, revision: 1, updated_at: new Date().toISOString() }; }

function demoBootstrap(): Bootstrap {
  const now = "2026-08-13T08:00:00.000Z";
  const instruments: Instrument[] = [
    { instrument_id: "CRYPTO_BTC_USD", provider_id: "COINBASE_EXCHANGE", symbol: "BTC", display_name: "Bitcoin", asset_class: "CRYPTO", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_close: 118420.32, latest_observed_at: "2026-08-13T07:00:00.000Z", latest_interval: "HOUR" },
    { instrument_id: "CRYPTO_ETH_USD", provider_id: "COINBASE_EXCHANGE", symbol: "ETH", display_name: "Ethereum", asset_class: "CRYPTO", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_close: 4628.74, latest_observed_at: "2026-08-13T07:00:00.000Z", latest_interval: "HOUR" },
    { instrument_id: "CRYPTO_SOL_USD", provider_id: "COINBASE_EXCHANGE", symbol: "SOL", display_name: "Solana", asset_class: "CRYPTO", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_close: 214.18, latest_observed_at: "2026-08-13T07:00:00.000Z", latest_interval: "HOUR" },
    { instrument_id: "ETF_SPY", provider_id: "ALPHA_VANTAGE", symbol: "SPY", display_name: "SPDR S&P 500 ETF Trust", asset_class: "US_ETF", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_close: 698.42, latest_observed_at: "2026-08-12T00:00:00.000Z", latest_interval: "DAY" },
    { instrument_id: "ETF_QQQ", provider_id: "ALPHA_VANTAGE", symbol: "QQQ", display_name: "Invesco QQQ Trust", asset_class: "US_ETF", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_close: 625.31, latest_observed_at: "2026-08-12T00:00:00.000Z", latest_interval: "DAY" },
    { instrument_id: "EQUITY_AAPL", provider_id: "ALPHA_VANTAGE", symbol: "AAPL", display_name: "Apple Inc.", asset_class: "US_EQUITY", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_close: 249.83, latest_observed_at: "2026-08-12T00:00:00.000Z", latest_interval: "DAY" },
    { instrument_id: "EQUITY_MSFT", provider_id: "ALPHA_VANTAGE", symbol: "MSFT", display_name: "Microsoft Corporation", asset_class: "US_EQUITY", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_close: 558.12, latest_observed_at: "2026-08-12T00:00:00.000Z", latest_interval: "DAY" },
    { instrument_id: "EQUITY_NVDA", provider_id: "ALPHA_VANTAGE", symbol: "NVDA", display_name: "NVIDIA Corporation", asset_class: "US_EQUITY", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_close: 192.46, latest_observed_at: "2026-08-12T00:00:00.000Z", latest_interval: "DAY" },
  ];
  const macro: MacroPoint[] = [
    { instrument_id: "MACRO_CPI", symbol: "CPI", display_name: "Consumer Price Index", provider_id: "FRED", rights_classification: "ATTRIBUTION_REQUIRED", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_value: 324.8, previous_value: 323.9, unit: "INDEX", frequency: "MONTHLY", observed_at: "2026-07-01T00:00:00.000Z" },
    { instrument_id: "MACRO_UNRATE", symbol: "UNRATE", display_name: "Unemployment Rate", provider_id: "FRED", rights_classification: "ATTRIBUTION_REQUIRED", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_value: 4.2, previous_value: 4.1, unit: "PERCENT", frequency: "MONTHLY", observed_at: "2026-07-01T00:00:00.000Z" },
    { instrument_id: "MACRO_DGS10", symbol: "DGS10", display_name: "10-Year Treasury Yield", provider_id: "FRED", rights_classification: "ATTRIBUTION_REQUIRED", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_value: 4.31, previous_value: 4.28, unit: "PERCENT", frequency: "DAILY", observed_at: "2026-08-12T00:00:00.000Z" },
    { instrument_id: "MACRO_T10Y2Y", symbol: "10Y2Y", display_name: "10Y–2Y Treasury Spread", provider_id: "FRED", rights_classification: "ATTRIBUTION_REQUIRED", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_value: 0.46, previous_value: 0.42, unit: "PERCENT", frequency: "DAILY", observed_at: "2026-08-12T00:00:00.000Z" },
    { instrument_id: "MACRO_DOLLAR", symbol: "USD", display_name: "Broad U.S. Dollar Index", provider_id: "FRED", rights_classification: "ATTRIBUTION_REQUIRED", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_value: 119.2, previous_value: 119.7, unit: "INDEX", frequency: "DAILY", observed_at: "2026-08-12T00:00:00.000Z" },
    { instrument_id: "MACRO_TREASURY_DEBT", symbol: "USDEBT", display_name: "Total Public Debt Outstanding", provider_id: "US_TREASURY_FISCALDATA", rights_classification: "PRIVATE_FOUNDER_RESEARCH", status: "OPERATIONAL", detail_code: "COLLECTION_SUCCEEDED", last_success_at: now, latest_value: 38_614_000_000_000, previous_value: 38_598_000_000_000, unit: "USD", frequency: "DAILY", observed_at: "2026-08-12T00:00:00.000Z" },
  ];
  const records: ResearchRecord[] = [
    { ...emptyRecord(), record_id: "1", record_type: "THESIS", instrument_id: "EQUITY_AAPL", title: "Services mix supports margin resilience", body: "Track Services growth against hardware replacement cycles; invalidate if gross margin compression persists for two filings.", status: "ACTIVE", confidence: 62, tags_json: '["quality","margin"]', revision: 4, updated_at: "2026-08-13T06:20:00.000Z" },
    { ...emptyRecord(), record_id: "2", record_type: "TASK", title: "Review July CPI composition", body: "Separate shelter, services ex-housing, and goods contribution before updating the macro base case.", status: "ACTIVE", due_at: "2026-08-14T10:00:00.000Z", revision: 2, updated_at: "2026-08-13T05:15:00.000Z" },
    { ...emptyRecord(), record_id: "3", record_type: "CATALYST", instrument_id: "EQUITY_NVDA", title: "NVDA quarterly filing", body: "Compare data-center revenue, inventory, and customer concentration with the existing thesis.", status: "WATCHING", due_at: "2026-08-26T20:00:00.000Z", revision: 1, updated_at: "2026-08-12T18:00:00.000Z" },
    { ...emptyRecord(), record_id: "4", record_type: "RISK", instrument_id: "CRYPTO_BTC_USD", title: "Liquidity regime reversal", body: "Treat a sustained real-yield rise with broad-dollar strength as a thesis review trigger, not an automatic trade signal.", status: "WATCHING", confidence: 48, tags_json: '["macro","liquidity"]', revision: 3, updated_at: "2026-08-12T15:45:00.000Z" },
  ];
  const provider_health = instruments.map((instrument) => ({ provider_id: instrument.provider_id, instrument_id: instrument.instrument_id, symbol: instrument.symbol, display_name: instrument.display_name, status: "OPERATIONAL", last_attempt_at: now, last_success_at: now, next_due_at: "2026-08-13T09:00:00.000Z", detail_code: "COLLECTION_SUCCEEDED", quota_state: "WITHIN_CONFIGURED_BUDGET", rights_classification: instrument.rights_classification }));
  return { instruments, watchlists: [{ watchlist_id: "demo", name: "Core watchlist", revision: 7, items: instruments.map((item) => item.instrument_id) }], records, macro, provider_health, csrf_token: "demo", session_expires_at: "2026-08-13T16:00:00.000Z", generated_at: now, boundary: "NON_RAB1_RESEARCH_ONLY", authority_effect: "NONE" };
}

function demoDossier(): Dossier {
  const data = demoBootstrap();
  const bars = Array.from({ length: 100 }, (_, index) => ({ observed_at: new Date(Date.UTC(2026, 3, 1 + index)).toISOString(), close: 208 + index * .38 + Math.sin(index / 5) * 7 + Math.cos(index / 13) * 3 }));
  return { instrument: data.instruments.find((item) => item.instrument_id === "EQUITY_AAPL")!, bars, metrics: { latest: bars.at(-1)?.close ?? null, return_1d: .006, return_30d: .084, realized_volatility: .218, maximum_drawdown: -.071, distance_from_high: -.014, observation_count: 100, window: `${bars[0].observed_at}/${bars.at(-1)?.observed_at}` }, fundamentals: [{ metric_key: "Assets", value: 364_980_000_000, period_end: "2026-06-27", form: "10-Q" }, { metric_key: "Revenues", value: 98_420_000_000, period_end: "2026-06-27", form: "10-Q" }, { metric_key: "NetIncomeLoss", value: 24_780_000_000, period_end: "2026-06-27", form: "10-Q" }, { metric_key: "StockholdersEquity", value: 71_360_000_000, period_end: "2026-06-27", form: "10-Q" }] };
}

function demoComparison(): Comparison {
  const ids = ["CRYPTO_BTC_USD", "CRYPTO_ETH_USD", "CRYPTO_SOL_USD"];
  const points = Array.from({ length: 90 }, (_, index) => ({ observed_at: new Date(Date.UTC(2026, 5, 1, index)).toISOString(), normalized: Object.fromEntries(ids.map((id, offset) => [id, 100 + index * (0.12 + offset * .05) + Math.sin(index / (5 + offset)) * (2 + offset)])) }));
  return { points, correlations: { CRYPTO_BTC_USD: 1, CRYPTO_ETH_USD: .81, CRYPTO_SOL_USD: .67 }, beta_to_first: { CRYPTO_BTC_USD: 1, CRYPTO_ETH_USD: 1.18, CRYPTO_SOL_USD: 1.46 } };
}
