import Image from "next/image";
import Link from "next/link";

const FOUNDER_RESEARCH_URL = "https://deltagrid-founder-gateway.tushar142004.workers.dev/research";

const coverage = [
  ["Markets", "8", "3 crypto · 3 equities · 2 ETFs"],
  ["Macro series", "9", "8 FRED · US Treasury debt"],
  ["Company mappings", "3", "AAPL · MSFT · NVDA"],
  ["Research record types", "7", "Notes through tasks"],
] as const;

const dataContract = [
  ["Coinbase Exchange", "Hourly", "240 settled bars / capture"],
  ["Alpha Vantage", "Daily", "Up to 100 delayed bars"],
  ["FRED", "Daily check", "Up to 120 observations / series"],
  ["SEC XBRL", "Daily check", "5 fixed company concepts"],
  ["Treasury Fiscal Data", "Daily check", "Latest Debt to the Penny"],
] as const;

const features = [
  ["Cockpit", "Watchlist prices, collection freshness, open research tasks, catalysts, and recent revisions."],
  ["Asset dossier", "Timestamped price history, returns, realized volatility, drawdown, and SEC facts where available."],
  ["Compare", "Aligned normalized performance, correlation, beta, volatility, and drawdown for up to four instruments."],
  ["Macro", "Inflation, employment, rates, yields, spreads, GDP, dollar index, and federal debt with release context."],
  ["Notebook", "Founder-authored notes, theses, evidence, journals, catalysts, risks, and tasks with revision history."],
  ["Data health", "Per-instrument provider status, latest success, next collection, quota state, rights, and error code."],
] as const;

const snapshots = [
  ["/snapshots/research-cockpit.png", "Research cockpit", "Watchlist, work queue, catalysts, and collection health."],
  ["/snapshots/asset-dossier.png", "Asset dossier", "Observed prices, deterministic metrics, facts, and thesis structure."],
  ["/snapshots/compare-macro.png", "Compare and macro", "Aligned series and timestamped economic context."],
] as const;

export function ResearchLanding() {
  return (
    <main className="landing-main">
      <section className="landing-hero">
        <div className="landing-copy">
          <p className="eyebrow">DeltaGrid Research Engine</p>
          <h1>A private market research workspace.</h1>
          <p className="lede">Delayed market data, macro releases, public-company facts, deterministic analytics, and revisioned research notes in one founder-only interface.</p>
          <div className="landing-actions">
            <a className="founder-login" href={FOUNDER_RESEARCH_URL}><span>Invite only</span>Founder access <b>↗</b></a>
            <Link className="text-link" href="/system">Public system status</Link>
          </div>
          <p className="landing-disclaimer">Research only. No brokerage connection, orders, paper trading, capital, or execution authority.</p>
        </div>
        <div className="coverage-board" aria-label="Configured research coverage">
          <div className="coverage-head"><span>Configured scope</span><b>20 instrument mappings</b></div>
          <div className="coverage-grid">
            {coverage.map(([label, value, note]) => <div key={label}><span>{label}</span><strong>{value}</strong><small>{note}</small></div>)}
          </div>
          <p><strong>Mission 104: NOT AUTHORIZED</strong><span>Verified projection · no private or protected values</span></p>
        </div>
      </section>

      <section className="data-contract" aria-label="Research data contract">
        <div className="data-contract-head"><p className="eyebrow">Data contract</p><h2>Five independent public-data sources</h2><p>Missing, stale, malformed, or quota-limited responses remain explicit. The system does not invent a current value.</p></div>
        <div className="data-contract-table">
          <div className="data-contract-row table-label"><span>Provider</span><span>Collection</span><span>Bounded response</span></div>
          {dataContract.map(([provider, cadence, limit]) => <div className="data-contract-row" key={provider}><strong>{provider}</strong><span>{cadence}</span><span>{limit}</span></div>)}
        </div>
      </section>

      <section className="landing-section compact-section">
        <div className="section-heading"><p className="eyebrow">Workspace</p><h2>Six working views, one research record.</h2><p>Every displayed metric identifies its source, observation time, calculation window, and adjustment state.</p></div>
        <div className="feature-grid">{features.map(([title, body], index) => <article key={title}><span>{String(index + 1).padStart(2, "0")}</span><h3>{title}</h3><p>{body}</p></article>)}</div>
      </section>

      <section className="landing-section snapshot-section compact-section">
        <div className="section-heading"><p className="eyebrow">Interface</p><h2>Sanitized product views</h2><p>The previews use deterministic fixtures. Founder notes, private live state, and protected RAB-1 evidence are never used for public screenshots.</p></div>
        <div className="snapshot-grid">{snapshots.map(([src, title, caption]) => <figure key={src}><div><Image src={src} alt={`Sanitized DeltaGrid ${title} product screenshot`} width={1440} height={900} /></div><figcaption><strong>{title}</strong><span>{caption}</span></figcaption></figure>)}</div>
      </section>

      <section className="landing-section security-section compact-section">
        <div><p className="eyebrow">Access boundary</p><h2>One founder identity. MFA enforced.</h2></div>
        <div className="security-list"><p><strong>Private route</strong><span>The existing Cloudflare Access application protects the founder hostname. The Worker separately validates the Access JWT and exact founder identity.</span></p><p><strong>Research isolation</strong><span>Research tables are scoped to the verified founder and labeled NON_RAB1_RESEARCH_ONLY with authority effect NONE.</span></p><p><strong>Execution closed</strong><span>No provider key reaches the browser, and no route can place, simulate, authorize, or fund an order.</span></p></div>
      </section>

      <section className="landing-cta"><div><p className="eyebrow">Private workspace</p><h2>Invite only</h2><p>There is no public signup. The observer remains public and read-only; the research workspace remains founder-only.</p></div><a className="founder-login" href={FOUNDER_RESEARCH_URL}><span>Invite only</span>Open research engine <b>↗</b></a></section>
    </main>
  );
}
