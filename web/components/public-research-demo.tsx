"use client";

import { useState } from "react";
import {
  DEMO_NAV,
  PUBLIC_DEMO_IDENTITY,
  demoDatasetCustody,
  demoHealth,
  demoHypotheses,
  demoIntelligence,
  demoMacro,
  demoMarketSeries,
  demoNotebook,
  demoOperatorWorkflow,
  demoResearchGates,
  demoSystemBoundary,
  demoTasks,
  demoTrialLedger,
  demoWatchlist,
  type DemoView,
} from "../lib/public-demo-data";
import styles from "./public-research-demo.module.css";

const FOUNDER_RESEARCH_URL = "https://deltagrid-founder-gateway.tushar142004.workers.dev/research";

export function PublicResearchDemo() {
  const [view, setView] = useState<DemoView>("cockpit");
  const current = DEMO_NAV.find((item) => item.id === view) ?? DEMO_NAV[0];

  return (
    <main className={styles.page}>
      <section className={styles.banner} aria-label="Demo mode disclosure">
        <div><strong>DEMO MODE</strong><span>SANITIZED FIXTURES · NOT LIVE · NO WRITES</span></div>
        <a href={FOUNDER_RESEARCH_URL}>Log in for Founder Mode ↗</a>
      </section>

      <section className={styles.shell}>
        <aside className={styles.sidebar}>
          <div className={styles.demoBrand}><span aria-hidden="true">Δ</span><div><strong>DeltaGrid</strong><small>Research Engine</small></div></div>
          <nav className={styles.demoNav} aria-label="Demo research workspace">
            {DEMO_NAV.map((item) => (
              <button type="button" key={item.id} className={view === item.id ? styles.active : undefined} onClick={() => setView(item.id)}>
                <span aria-hidden="true">{item.glyph}</span>{item.label}
              </button>
            ))}
          </nav>
          <div className={styles.boundaryBox}><span>PUBLIC SANITIZED DEMO</span><strong>AUTHORITY NONE</strong><p>Same product concepts. Deterministic fixture data. No founder records.</p></div>
        </aside>

        <div className={styles.workspace}>
          <header className={styles.workspaceHeader}>
            <div><p>Public product workspace</p><h1>{current.label}</h1></div>
            <div className={styles.workspaceMeta}><span>● Fixture healthy</span><small>{PUBLIC_DEMO_IDENTITY.generated_label}</small></div>
          </header>
          {view === "cockpit" ? <Cockpit /> : null}
          {view === "intelligence" ? <Intelligence /> : null}
          {view === "hypotheses" ? <Hypotheses /> : null}
          {view === "gates" ? <ResearchGates /> : null}
          {view === "markets" ? <Markets /> : null}
          {view === "compare" ? <Compare /> : null}
          {view === "macro" ? <Macro /> : null}
          {view === "notebook" ? <Notebook /> : null}
          {view === "health" ? <DataHealth /> : null}
          {view === "system" ? <SystemBoundary /> : null}
        </div>
      </section>

      <section className={styles.explainer}>
        <div><span>01</span><strong>What is real?</strong><p>The navigation, workflow concepts, evidence discipline, product structure and authority boundaries mirror DeltaGrid.</p></div>
        <div><span>02</span><strong>What is synthetic?</strong><p>Every value inside this Demo Mode is deterministic fixture data created only to demonstrate the interface safely.</p></div>
        <div><span>03</span><strong>What does login unlock?</strong><p>Your allowed founder identity reaches the authenticated workspace with real private records and supported controls.</p></div>
      </section>
    </main>
  );
}

function Cockpit() {
  const openTasks = demoTasks.filter((task) => task.status === "OPEN").length;
  return <div className={styles.stack}>
    <section className={styles.metricGrid}>
      <Metric label="Demo instruments" value={String(demoWatchlist.length)} note="Synthetic mappings" />
      <Metric label="Open research tasks" value={String(openTasks)} note="Fixture queue" />
      <Metric label="Hypotheses" value={String(demoHypotheses.length)} note="Structured examples" />
      <Metric label="Authority effect" value="NONE" note="Public mode cannot act" />
    </section>
    <div className={styles.twoColumn}>
      <Panel title="Watchlist" eyebrow="Normalized fixture indices" meta="Baseline 100">
        <div className={styles.watchlist}>{demoWatchlist.map((item) => <div key={item.symbol}><span><b>{item.symbol}</b><small>{item.name}</small></span><strong>{item.index.toFixed(1)}</strong><em className={item.change >= 0 ? styles.up : styles.down}>{item.change >= 0 ? "+" : ""}{item.change.toFixed(1)}%</em></div>)}</div>
      </Panel>
      <Panel title="Research queue" eyebrow="Revisioned workflow preview" meta="No persistence">
        <div className={styles.taskList}>{demoTasks.map((task) => <article key={task.title}><span>{task.type}</span><strong>{task.title}</strong><small>{task.status} · {task.due}</small></article>)}</div>
      </Panel>
    </div>
    <Panel title="Operator workflow" eyebrow="Why each lane can or cannot advance" meta="Sanitized decision queue">
      <div className={styles.notebookTable}><div className={styles.tableHead}><span>Lane</span><span>Gate</span><span>State</span><span>Next safe action</span></div>{demoOperatorWorkflow.map((item) => <div key={item.lane}><strong>{item.lane}</strong><span>{item.gate}</span><span>{item.state}</span><small>{item.next}</small></div>)}</div>
    </Panel>
  </div>;
}

function Intelligence() {
  const breadth = demoIntelligence.breadth;
  return <div className={styles.stack}>
    <section className={styles.metricGrid}>
      <Metric label="Positive" value={String(breadth.positive)} note="Synthetic breadth" />
      <Metric label="Negative" value={String(breadth.negative)} note="Synthetic breadth" />
      <Metric label="Flat" value={String(breadth.flat)} note="Synthetic breadth" />
      <Metric label="Unavailable" value={String(breadth.unavailable)} note="Fail-closed coverage" />
    </section>
    <div className={styles.twoColumn}>
      <Panel title="Observed pressure" eyebrow="Questions, not signals" meta="Fixture only"><div className={styles.cardList}>{demoIntelligence.risk.map((item) => <article key={item.label}><span>{item.label}</span><strong>{item.value}</strong><p>{item.note}</p></article>)}</div></Panel>
      <Panel title="Candidate questions" eyebrow="Research attention" meta="Authority NONE"><div className={styles.cardList}>{demoIntelligence.priorities.map((item) => <article key={item.kind}><span>{item.kind.replaceAll("_", " ")}</span><strong>{item.symbol} · {item.value}</strong><p>{item.metric} · {item.status}</p></article>)}</div></Panel>
    </div>
  </div>;
}

function Hypotheses() {
  return <div className={styles.stack}>
    <div className={styles.notice}><strong>PREREGISTRATION PREVIEW</strong><span>Scientific intent can be reviewed publicly; canonical dataset, permit, execution and statistical bindings remain unresolved here.</span></div>
    <div className={styles.hypothesisGrid}>{demoHypotheses.map((item) => <article key={item.id}><div className={styles.hypothesisTop}><span>{item.status}</span><small>{item.id} · REV {item.revision}</small></div><h2>{item.title}</h2><dl><div><dt>Mechanism</dt><dd>{item.mechanism}</dd></div><div><dt>Falsification</dt><dd>{item.falsification}</dd></div><div><dt>Finite budget</dt><dd>{item.budget}</dd></div><div><dt>Canonical handoff</dt><dd>{item.bindings}</dd></div></dl></article>)}</div>
  </div>;
}

function ResearchGates() {
  return <div className={styles.stack}>
    <section className={styles.metricGrid}>
      <Metric label="Validated alpha" value="NONE" note="Truthful current state" />
      <Metric label="Selected candidate" value="NONE" note="No promotion claim" />
      <Metric label="Protected opening" value="CLOSED" note="RAB-1 / M104 unchanged" />
      <Metric label="Execution authority" value="NONE" note="No paper/live/capital action" />
    </section>
    <Panel title="Research admission path" eyebrow="Founder workflow concepts" meta="Sanitized read-only model">
      <div className={styles.cardList}>{demoResearchGates.map((gate) => <article key={gate.stage}><span>{gate.state}</span><strong>{gate.stage}</strong><p>{gate.detail}</p></article>)}</div>
    </Panel>
    <Panel title="Trial and accounting preview" eyebrow="Finite deterministic fixture" meta="No persistence or writes">
      <div className={styles.notebookTable}><div className={styles.tableHead}><span>Binding</span><span>Value</span><span>Status</span><span>Effect</span></div>{demoTrialLedger.map((item) => <div key={item.field}><strong>{item.field}</strong><span>{item.value}</span><span>{item.status}</span><small>NONE</small></div>)}</div>
    </Panel>
    <div className={styles.notice}><strong>FAIL-CLOSED DEMO</strong><span>Admission, trial reservation, protected opening, execution and accounting remain illustrative only. The public observer cannot create permits, consume budgets, open protected stages, place orders or move capital.</span></div>
  </div>;
}

function Markets() {
  const latest = demoMarketSeries.at(-1)!;
  return <div className={styles.stack}>
    <section className={styles.metricGrid}>
      <Metric label="Selected fixture" value="SYN-A" note="Synthetic Growth Basket" />
      <Metric label="Normalized level" value={latest.a.toFixed(1)} note="Not a market price" />
      <Metric label="Window" value="7" note="Fixture observations" />
      <Metric label="Rights" value="DEMO" note="No redistributed vendor values" />
    </section>
    <Panel title="Synthetic asset dossier" eyebrow="Normalized history" meta="Deterministic fixture"><MiniSeries /><div className={styles.dossierGrid}><div><span>Observation contract</span><strong>Timestamped normalized values</strong><p>No current market-value claim.</p></div><div><span>Risk summary</span><strong>Illustrative volatility</strong><p>Shows where deterministic metrics appear in Founder Mode.</p></div><div><span>Research context</span><strong>Linked thesis records</strong><p>Public demo records are not founder records.</p></div></div></Panel>
  </div>;
}

function Compare() {
  const max = Math.max(...demoMarketSeries.flatMap((point) => [point.a, point.b, point.c]));
  return <div className={styles.stack}>
    <Panel title="Normalized comparison" eyebrow="All series start at 100" meta="Synthetic indices"><div className={styles.compareChart} aria-label="Synthetic normalized comparison">{demoMarketSeries.map((point) => <div key={point.t} className={styles.compareColumn}><div className={styles.bars}><i style={{ height: `${(point.a / max) * 100}%` }} /><i style={{ height: `${(point.b / max) * 100}%` }} /><i style={{ height: `${(point.c / max) * 100}%` }} /></div><small>{point.t}</small></div>)}</div><div className={styles.legend}><span>■ SYN-A</span><span>■ SYN-B</span><span>■ SYN-C</span></div></Panel>
    <section className={styles.metricGrid}><Metric label="SYN-A / SYN-B" value="0.34" note="Fixture correlation" /><Metric label="SYN-A / SYN-C" value="0.71" note="Fixture correlation" /><Metric label="SYN-B / SYN-C" value="-0.18" note="Fixture correlation" /><Metric label="Alignment" value="EXACT" note="Shared fixture timestamps" /></section>
  </div>;
}

function Macro() {
  return <div className={styles.stack}><div className={styles.macroGrid}>{demoMacro.map((item) => <article key={item.series}><span>{item.series}</span><strong>{item.latest.toFixed(1)}</strong><p>{item.unit}</p><small>{item.direction.toUpperCase()} from {item.previous.toFixed(1)}</small></article>)}</div><div className={styles.notice}><strong>NO LIVE MACRO VALUES</strong><span>Founder Mode shows source-aware observations and release context. Demo Mode uses normalized synthetic values so the interface can be public without implying freshness.</span></div></div>;
}

function Notebook() {
  return <div className={styles.stack}><Panel title="Research memory" eyebrow="Revisioned record model" meta="Demo records only"><div className={styles.notebookTable}><div className={styles.tableHead}><span>Type</span><span>Title</span><span>Status</span><span>Revision</span></div>{demoNotebook.map((item) => <div key={item.title}><span>{item.type}</span><strong>{item.title}</strong><span>{item.status}</span><small>r{item.revision} · {item.updated}</small></div>)}</div></Panel><div className={styles.notice}><strong>READ-ONLY DEMO</strong><span>Create, edit, revision history and founder-scoped persistence are available only after authenticated Founder Mode login.</span></div></div>;
}

function DataHealth() {
  return <div className={styles.stack}>
    <section className={styles.metricGrid}><Metric label="Configured demo sources" value={String(demoHealth.length)} note="Provider categories" /><Metric label="Healthy" value={String(demoHealth.filter((item) => item.status === "HEALTHY").length)} note="Fixture status" /><Metric label="Degraded" value={String(demoHealth.filter((item) => item.status === "DEGRADED").length)} note="Explicit failure state" /><Metric label="Credentials exposed" value="0" note="Public boundary" /></section>
    <Panel title="Provider health" eyebrow="Fail-closed status model" meta="Synthetic diagnostics"><div className={styles.healthTable}>{demoHealth.map((item) => <div key={item.provider}><span className={item.status === "HEALTHY" ? styles.healthGood : styles.healthWarn}>● {item.status}</span><strong>{item.provider}</strong><small>{item.scope}</small><small>{item.freshness}</small><em>{item.rights}</em></div>)}</div></Panel>
    <Panel title="Dataset custody" eyebrow="Identity, chronology, rights and evidence chain" meta="Sanitized deterministic bindings">
      <div className={styles.notebookTable}><div className={styles.tableHead}><span>Binding</span><span>Value</span><span>State</span><span>Evidence</span></div>{demoDatasetCustody.map((item) => <div key={item.binding}><strong>{item.binding}</strong><span>{item.value}</span><span>{item.state}</span><small>{item.evidence}</small></div>)}</div>
    </Panel>
    <div className={styles.notice}><strong>NO PRIVATE CUSTODY MATERIAL</strong><span>The observer demonstrates the evidence-chain model without exposing founder dataset metadata, provider payloads, production checksums, credentials or private operating receipts.</span></div>
  </div>;
}

function SystemBoundary() {
  return <div className={styles.stack}>
    <section className={styles.metricGrid}>
      <Metric label="Public surface" value="SANITIZED" note="Deterministic fixtures" />
      <Metric label="Founder surface" value="ACCESS CONTROLLED" note="Private authenticated boundary" />
      <Metric label="Release provenance" value="UNVERIFIED" note="No deployed-revision claim" />
      <Metric label="Public authority" value="NONE" note="Read-only observer" />
    </section>
    <Panel title="Public / founder boundary" eyebrow="Deployment and authority model" meta="Fail-closed representation">
      <div className={styles.cardList}>{demoSystemBoundary.map((item) => <article key={item.layer}><span>{item.state}</span><strong>{item.layer}</strong><p>{item.detail}</p></article>)}</div>
    </Panel>
    <div className={styles.notice}><strong>MERGED ≠ CI-GREEN ≠ DEPLOYED</strong><span>The observer treats source revision, verification and production provenance as separate facts. Private capability remains private even when its workflow concepts are demonstrated publicly.</span></div>
  </div>;
}

function MiniSeries() {
  const points = demoMarketSeries.map((point) => point.a);
  const low = Math.min(...points);
  const high = Math.max(...points);
  return <div className={styles.spark} aria-label="Synthetic normalized series">{points.map((value, index) => { const height = 30 + ((value - low) / Math.max(high - low, 1)) * 70; return <i key={`${demoMarketSeries[index].t}-${value}`} style={{ height: `${height}%` }} title={`${demoMarketSeries[index].t}: ${value.toFixed(1)}`} />; })}</div>;
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <article className={styles.metric}><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}

function Panel({ title, eyebrow, meta, children }: { title: string; eyebrow: string; meta: string; children: React.ReactNode }) {
  return <section className={styles.panel}><header><div><span>{eyebrow}</span><h2>{title}</h2></div><small>{meta}</small></header>{children}</section>;
}
