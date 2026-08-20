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
  ["M101", "DATA / ADMISSION AUTHORITY", "GATED"],
  ["M102", "EXPERIMENT ENGINE", "GATED"],
  ["M103", "PRE-RESULT GOVERNANCE", "PREPARED"],
  ["Mission 104", "CAPITAL AUTHORITY", "NOT AUTHORIZED"],
] as const;

const dataContract = [
  ["Coinbase Exchange", "Hourly", "240 settled bars / capture"],
  ["Alpha Vantage", "Daily", "Up to 100 delayed bars"],
  ["FRED", "Daily check", "Up to 120 observations / series"],
  ["SEC XBRL", "Daily check", "5 fixed company concepts"],
  ["Treasury Fiscal Data", "Daily check", "Latest Debt to the Penny"],
] as const;

const features = [
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
      <div className={styles.topbar}>
        <strong>DELTAGRID / PUBLIC RESEARCH OBSERVER</strong>
        <span>SYSTEM BOUNDARY: HEALTHY</span>
      </div>

      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <p className={styles.kicker}>Quantitative research infrastructure</p>
          <h1>Research first. Authority separate.</h1>
          <p>
            DeltaGrid is a falsification-led market research system built around reproducible data,
            explicit evidence, deterministic controls, and hard separation between research capability
            and trading authority.
          </p>
          <div className={styles.actions}>
            <Link className={styles.action} href="/research">Open public demo →</Link>
            <a className={styles.secondaryAction} href={FOUNDER_RESEARCH_URL}>Founder access ↗</a>
          </div>
          <p className={styles.disclaimer}>
            RESEARCH ONLY // NO BROKER CONNECTION // NO ORDERS // NO PAPER/LIVE TRADING // NO CAPITAL AUTHORITY
          </p>
        </div>

        <div className={styles.status} aria-label="Configured public research scope">
          <div className={styles.statusHead}><span>CONFIGURED SCOPE</span><span>PUBLIC / SANITIZED</span></div>
          <div className={styles.metricGrid}>
            {coverage.map(([label, value, note]) => (
              <div className={styles.metric} key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
                <small>{note}</small>
              </div>
            ))}
          </div>
          <div className={styles.statusFoot}><strong>Mission 104 NOT AUTHORIZED</strong><span>NO PRIVATE OR PROTECTED VALUES</span></div>
        </div>
      </section>

      <section className={styles.band} aria-label="Research authority state">
        {authority.map(([code, label, state]) => (
          <div key={code}>
            <span>{code} / {label}</span>
            <strong>{state}</strong>
          </div>
        ))}
      </section>

      <section className={styles.section}>
        <div className={styles.panel}>
          <p className={styles.sectionLabel}>DATA CONTRACT</p>
          <h2>Public inputs remain bounded and inspectable.</h2>
          <p>Missing, stale, malformed, or quota-limited responses stay explicit. The system does not manufacture a current value.</p>
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

      <section className={styles.workspace} aria-label="Public research workspace views">
        {features.map(([title, body], index) => (
          <article key={title}>
            <code>{String(index + 1).padStart(2, "0")}</code>
            <h3>{title}</h3>
            <p>{body}</p>
          </article>
        ))}
      </section>

      <section className={styles.previews} aria-label="Sanitized product previews">
        {snapshots.map(([src, title, caption]) => (
          <figure className={styles.preview} key={src}>
            <Image src={src} alt={`Sanitized DeltaGrid ${title} product screenshot`} width={1440} height={900} />
            <figcaption><strong>{title}</strong><span>{caption}</span></figcaption>
          </figure>
        ))}
      </section>

      <section className={styles.boundary}>
        <div className={styles.boundaryLead}>
          <p className={styles.sectionLabel}>ACCESS / AUTHORITY BOUNDARY</p>
          <h2>Public observer outside. Founder system inside.</h2>
        </div>
        <div className={styles.boundaryRows}>
          <p><strong>PUBLIC SURFACE</strong><span>Static observer and deterministic Demo Mode. No private research records or authenticated API state are included in the public build.</span></p>
          <p><strong>FOUNDER GATEWAY</strong><span>Cloudflare Access is the outer gate; the Worker independently validates the Access JWT and exact founder identity.</span></p>
          <p><strong>RESEARCH STATE</strong><span>Founder research records remain scoped to the verified founder and retain authority effect NONE unless a separate trusted-local workflow grants a narrower capability.</span></p>
          <p><strong>EXECUTION</strong><span>No public route can place, simulate, authorize, or fund an order. Provider secrets do not reach the browser.</span></p>
        </div>
      </section>
    </main>
  );
}
