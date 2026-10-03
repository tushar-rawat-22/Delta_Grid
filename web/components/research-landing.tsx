import Link from "next/link";
import { alphaSearchBRecord } from "../lib/public-research-record";
import styles from "./research-landing.module.css";

const researchStatus = [
  ["Question", "Spot trade-flow after costs?"],
  ["Stage", "Development closed"],
  ["Evidence", `${alphaSearchBRecord.sourceRecords.length} linked source records`],
  ["Decision", `${alphaSearchBRecord.rejectedCandidateCount} of ${alphaSearchBRecord.candidateCount} rejected`],
  ["Published", alphaSearchBRecord.publicationDateLabel],
  ["Authority", `Effect ${alphaSearchBRecord.authorityEffect}`],
] as const;

const programme = [
  ["RAB-1", "Prospective research programme", "LOCKED", "No result opened"],
  ["M101", "Data custody and admission", "GATED", "Metadata / permit boundary"],
  ["M102", "Development experiment engine", "GATED", "Exact admitted trials only"],
  ["M103", "Programme statistics and protected stages", "PREPARED", "Independent progression controls"],
] as const;

const mission104Authority = ["Mission 104", "Candidate observation", "NOT AUTHORIZED"] as const;

const coverage = [
  ["Markets", "8", "3 crypto · 3 equities · 2 ETFs"],
  ["Macro series", "9", "8 FRED · US Treasury debt"],
  ["Company mappings", "3", "AAPL · MSFT · NVDA"],
  ["Record types", "7", "Notes · theses · evidence · journals · catalysts · risks · tasks"],
] as const;

const dataContract = [
  ["Coinbase Exchange", "Hourly", "240 settled bars / capture"],
  ["Alpha Vantage", "Daily", "Up to 100 delayed bars"],
  ["FRED", "Daily check", "Up to 120 observations / series"],
  ["SEC XBRL", "Daily check", "5 fixed company concepts"],
  ["Treasury Fiscal Data", "Daily check", "Latest Debt to the Penny"],
] as const;

const workbench = [
  ["Research", "/research", "Sanitized research cockpit and deterministic Demo Mode."],
  ["Markets", "/markets", "Timestamped histories, metrics, risk summaries, and asset dossiers."],
  ["Evidence", "/evidence", "Publicly projected evidence and provenance records."],
  ["Risk", "/risk", "Current public risk and authority posture."],
  ["System", "/system", "Control architecture, boundaries, and operating state."],
  ["Missions", "/missions", "Implemented stages and explicitly closed future authority."],
] as const;

const boundary = [
  ["Public surface", "Static observer and deterministic sanitized Demo Mode."],
  ["Restricted workspace", "Invite-only, scoped, isolated, revocable, and unavailable without explicit founder approval plus fresh security/legal/authority review."],
  ["Private research", "Founder records, protected evidence, and private runtime state are not shipped in the public bundle."],
  ["Execution", "No public route can place, authorize, simulate, or fund an order. Provider secrets do not reach the browser."],
] as const;

function State({ value }: { value: string }) {
  const tone = value === "NOT AUTHORIZED" || value === "GATED" ? styles.stateBlocked : value === "PREPARED" || value === "LOCKED" ? styles.stateWatch : styles.stateNeutral;
  return <span className={`${styles.state} ${tone}`}>{value}</span>;
}

export function ResearchLanding() {
  return (
    <main className={styles.shell}>
      <header className={styles.masthead}>
        <div className={styles.identity}>
          <p className={styles.kicker}>DeltaGrid / Research Cockpit</p>
          <h1>A quantitative research system built to reject weak claims.</h1>
          <p>
            Inspect the question, costs, controls, evidence and decision behind a real closed experiment.
            DeltaGrid currently has no validated alpha, selected candidate or trading authority.
          </p>
        </div>
        <div className={styles.actions}>
          <Link className={styles.primaryAction} href="/evidence#alpha-search-b">Inspect rejected experiment</Link>
          <Link className={styles.secondaryAction} href="/research">Open sanitized demo</Link>
        </div>
      </header>

      <section className={styles.statusStrip} aria-label="Current research status">
        {researchStatus.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </section>

      <section className={styles.featuredRecord} aria-labelledby="featured-record-title">
        <div className={styles.recordStory}>
          <div className={styles.recordHeading}>
            <div>
              <p className={styles.recordEyebrow}><span>Closed record</span> {alphaSearchBRecord.label}</p>
              <h2 id="featured-record-title">{alphaSearchBRecord.question}</h2>
            </div>
            <span className={styles.rejectedState}>{alphaSearchBRecord.decisionLabel}</span>
          </div>
          <p className={styles.recordSummary}>{alphaSearchBRecord.summary}</p>
          <ol className={styles.lineage} aria-label="Alpha Search B experiment lineage">
            {alphaSearchBRecord.lineage.map(([index, label, detail]) => (
              <li key={label}>
                <span>{index}</span>
                <strong>{label}</strong>
                <p>{detail}</p>
              </li>
            ))}
          </ol>
          <Link className={styles.recordAction} href="/evidence#alpha-search-b">
            Inspect evidence and provenance <span aria-hidden="true">→</span>
          </Link>
        </div>

        <aside className={styles.stopPanel} aria-labelledby="why-stopped-title">
          <p className={styles.sectionCode}>Why it stopped</p>
          <h2 id="why-stopped-title">Failure is the finding.</h2>
          <p>Costs, sample gates, statistical controls and unchanged replication prevented a favorable-looking partial result from advancing.</p>
          <dl>
            <div><dt>Selected candidate</dt><dd>None</dd></div>
            <div><dt>Validation opened</dt><dd>No</dd></div>
            <div><dt>Holdout opened</dt><dd>No</dd></div>
            <div><dt>Paper / live trading</dt><dd>Not authorized</dd></div>
          </dl>
          <p className={styles.authorityNote}>No broker connection · no order path · public authority effect: NONE.</p>
        </aside>
      </section>

      <div className={styles.executiveGrid}>
        <section className={styles.primaryPanel} aria-labelledby="programme-title">
          <div className={styles.panelHeading}>
            <div>
              <p className={styles.sectionCode}>Programme</p>
              <h2 id="programme-title">Research progression</h2>
            </div>
            <p>Capability and authority remain separate. A built component does not grant the next stage.</p>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr><th>Stage</th><th>Mandate</th><th>State</th><th>Constraint</th></tr>
              </thead>
              <tbody>
                {programme.map(([stage, mandate, state, constraint]) => (
                  <tr key={stage}>
                    <td className={styles.code}>{stage}</td>
                    <td>{mandate}</td>
                    <td><State value={state} /></td>
                    <td className={styles.mutedCell}>{constraint}</td>
                  </tr>
                ))}
                <tr>
                  <td className={styles.code}>{mission104Authority[0]}</td>
                  <td>{mission104Authority[1]}</td>
                  <td><State value={mission104Authority[2]} /></td>
                  <td className={styles.mutedCell}>Requires a qualified holdout result</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <aside className={styles.sidePanel} aria-labelledby="posture-title">
          <p className={styles.sectionCode}>Posture</p>
          <h2 id="posture-title">Control posture</h2>
          <dl className={styles.controlList}>
            <div><dt>Broker connection</dt><dd>None</dd></div>
            <div><dt>Exchange credentials</dt><dd>Not authorized</dd></div>
            <div><dt>Orders</dt><dd>Not authorized</dd></div>
            <div><dt>Portfolio allocation</dt><dd>Not authorized</dd></div>
            <div><dt>Public write path</dt><dd>None</dd></div>
          </dl>
          <p className={styles.controlNote}>Public website state has authority effect NONE.</p>
        </aside>
      </div>

      <section className={styles.section} aria-labelledby="coverage-title">
        <div className={styles.panelHeading}>
          <div>
            <p className={styles.sectionCode}>Coverage</p>
            <h2 id="coverage-title">Configured research surface</h2>
          </div>
          <p>Counts describe the sanitized workspace configuration, not an investment universe or an authorization to collect new protected data.</p>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead><tr><th>Area</th><th>Count</th><th>Scope</th></tr></thead>
            <tbody>
              {coverage.map(([label, count, scope]) => (
                <tr key={label}><td>{label}</td><td className={styles.numeric}>{count}</td><td className={styles.mutedCell}>{scope}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className={styles.twoColumn}>
        <section className={styles.section} aria-labelledby="inputs-title">
          <div className={styles.panelHeading}>
            <div>
              <p className={styles.sectionCode}>Data</p>
              <h2 id="inputs-title">Public inputs</h2>
            </div>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th>Provider</th><th>Cadence</th><th>Bound</th></tr></thead>
              <tbody>
                {dataContract.map(([provider, cadence, bound]) => (
                  <tr key={provider}><td>{provider}</td><td>{cadence}</td><td className={styles.mutedCell}>{bound}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className={styles.footnote}>Stale and missing values remain explicit rather than being silently filled.</p>
        </section>

        <section className={styles.section} aria-labelledby="workbench-title">
          <div className={styles.panelHeading}>
            <div>
              <p className={styles.sectionCode}>Workbench</p>
              <h2 id="workbench-title">Review surfaces</h2>
            </div>
          </div>
          <div className={styles.routeList}>
            {workbench.map(([label, href, description]) => (
              <Link href={href} key={href} className={styles.routeRow}>
                <strong>{label}</strong><span>{description}</span><i aria-hidden="true">→</i>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <section className={styles.section} aria-labelledby="boundary-title">
        <div className={styles.panelHeading}>
          <div>
            <p className={styles.sectionCode}>Boundary</p>
            <h2 id="boundary-title">Public / restricted separation</h2>
          </div>
          <p>The observer is for inspection. It is not an execution console.</p>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <tbody>
              {boundary.map(([label, value]) => (
                <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
