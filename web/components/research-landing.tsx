import Image from "next/image";
import Link from "next/link";
import styles from "./research-landing.module.css";

const FOUNDER_RESEARCH_URL = "https://deltagrid-founder-gateway.tushar142004.workers.dev/research";

const coverage = [
  ["Markets", "8", "3 crypto · 3 equities · 2 ETFs"],
  ["Macro series", "9", "8 FRED · US Treasury debt"],
  ["Company mappings", "3", "AAPL · MSFT · NVDA"],
  ["Record types", "7", "Notes through tasks"],
] as const;

const authority = [
  ["M101", "Data and admission", "Gated"],
  ["M102", "Experiment engine", "Gated"],
  ["M103", "Pre-result programme", "Prepared"],
  ["Mission 104", "Candidate observation", "NOT AUTHORIZED"],
] as const;

const dataContract = [
  ["Coinbase Exchange", "Hourly", "240 settled bars / capture"],
  ["Alpha Vantage", "Daily", "Up to 100 delayed bars"],
  ["FRED", "Daily check", "Up to 120 observations / series"],
  ["SEC XBRL", "Daily check", "5 fixed company concepts"],
  ["Treasury Fiscal Data", "Daily check", "Latest Debt to the Penny"],
] as const;

const workspace = [
  ["Cockpit", "Watchlist, collection freshness, work queue, catalysts, revisions."],
  ["Intelligence", "Breadth, risk pressure, relationships, macro changes, candidate questions."],
  ["Hypotheses", "Thesis records, falsification logic, finite budgets, preregistration handoff."],
  ["Markets", "Timestamped histories, deterministic metrics, risk summaries, asset dossiers."],
  ["Compare", "Normalized performance, correlation, beta, volatility, drawdown."],
  ["Macro", "Inflation, employment, rates, yields, spreads, GDP, dollar, federal debt."],
  ["Notebook", "Notes, theses, evidence, journals, catalysts, risks, tasks, revisions."],
  ["Data health", "Provider status, cadence, quota state, rights, explicit failures."],
] as const;

const snapshots = [
  ["/snapshots/research-cockpit.png", "Research cockpit", "Watchlist, work queue, catalysts, collection health."],
  ["/snapshots/asset-dossier.png", "Asset dossier", "Observed prices, deterministic metrics, facts, thesis structure."],
  ["/snapshots/compare-macro.png", "Compare / macro", "Aligned series and timestamped economic context."],
] as const;

export function ResearchLanding() {
  return (
    <main className={styles.shell}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>DeltaGrid / public research observer</p>
          <h1>Research system status</h1>
          <p className={styles.intro}>
            Read-only view of the project&apos;s research scope, data sources, controls, and sanitized workspace.
            The private Founder system is separate from this build.
          </p>
        </div>
        <nav className={styles.links} aria-label="Research observer links">
          <Link href="/research">Open demo</Link>
          <a href={FOUNDER_RESEARCH_URL}>Founder access ↗</a>
        </nav>
      </header>

      <section className={styles.statusBlock} aria-labelledby="research-state-title">
        <h2 id="research-state-title">Current research state</h2>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <tbody>
              <tr><th scope="row">Research result</th><td>No validated alpha</td></tr>
              <tr><th scope="row">Selected candidate</th><td>None selected</td></tr>
              <tr><th scope="row">Paper / live trading</th><td>Disabled</td></tr>
              <tr><th scope="row">Mission 104</th><td>NOT AUTHORIZED</td></tr>
            </tbody>
          </table>
        </div>
        <p className={styles.note}>No broker connection. No paper/live trading. No capital authority.</p>
      </section>

      <div className={styles.split}>
        <section aria-labelledby="coverage-title">
          <h2 id="coverage-title">Configured coverage</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th>Area</th><th>Count</th><th>Scope</th></tr></thead>
              <tbody>
                {coverage.map(([label, value, note]) => (
                  <tr key={label}><td>{label}</td><td>{value}</td><td>{note}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section aria-labelledby="authority-title">
          <h2 id="authority-title">Authority</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th>Stage</th><th>Purpose</th><th>State</th></tr></thead>
              <tbody>
                {authority.map(([code, label, state]) => (
                  <tr key={code}><td>{code}</td><td>{label}</td><td>{state}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section className={styles.section} aria-labelledby="inputs-title">
        <div className={styles.sectionHeading}>
          <h2 id="inputs-title">Public data inputs</h2>
          <p>Provider limits and stale or missing values stay visible rather than being filled in.</p>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead><tr><th>Provider</th><th>Collection</th><th>Bounded response</th></tr></thead>
            <tbody>
              {dataContract.map(([provider, cadence, limit]) => (
                <tr key={provider}><td>{provider}</td><td>{cadence}</td><td>{limit}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="workspace-title">
        <div className={styles.sectionHeading}>
          <h2 id="workspace-title">Workspace</h2>
          <p>Demo Mode uses sanitized fixtures. Founder records and authenticated API state are not shipped in the public bundle.</p>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead><tr><th>View</th><th>What it is for</th></tr></thead>
            <tbody>
              {workspace.map(([title, body]) => (
                <tr key={title}><td>{title}</td><td>{body}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="preview-title">
        <div className={styles.sectionHeading}>
          <h2 id="preview-title">Sanitized interface</h2>
          <p>These screenshots are deterministic demo material, not private Founder state.</p>
        </div>
        <div className={styles.previews}>
          {snapshots.map(([src, title, caption]) => (
            <figure className={styles.preview} key={src}>
              <Image src={src} alt={`Sanitized DeltaGrid ${title} product screenshot`} width={1440} height={900} />
              <figcaption><strong>{title}</strong><span>{caption}</span></figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className={styles.section} aria-labelledby="boundary-title">
        <div className={styles.sectionHeading}>
          <h2 id="boundary-title">Public / founder boundary</h2>
          <p>The public observer is useful for review, but it has no path into private research or execution.</p>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <tbody>
              <tr><th scope="row">Public surface</th><td>Static observer and deterministic Demo Mode only.</td></tr>
              <tr><th scope="row">Founder Gateway</th><td>Cloudflare Access plus independent Worker identity validation.</td></tr>
              <tr><th scope="row">Research state</th><td>Private Founder records stay outside the public build and retain authority effect NONE unless a separate trusted-local workflow grants a narrower capability.</td></tr>
              <tr><th scope="row">Execution</th><td>No public route can place, simulate, authorize, or fund an order. Provider secrets do not reach the browser.</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
