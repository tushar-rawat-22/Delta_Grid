import Link from "next/link";
import styles from "./research-landing.module.css";

const statusTape = [
  ["Research result", "No validated alpha", "blocked"],
  ["Selected candidate", "None selected", "neutral"],
  ["Paper / live", "Disabled", "blocked"],
  ["Capital", "Blocked", "blocked"],
] as const;

const falsificationLoop = [
  ["01", "Hypothesis", "State the claim before touching evidence."],
  ["02", "Point-in-time data", "Use only information knowable at the decision timestamp."],
  ["03", "Experiment", "Run deterministic, pre-specified comparisons."],
  ["04", "Realistic costs", "Apply execution and friction assumptions before judging results."],
  ["05", "Falsification", "Try to break the claim with controls and adverse cases."],
  ["06", "Evidence", "Retain provenance, failures, and uncertainty."],
  ["07", "Decision", "Reject, archive, or advance only within explicit authority."],
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
          <p className={styles.kicker}>DeltaGrid / public research observer</p>
          <h1>Falsify the claim before trusting the result.</h1>
          <p>
            A read-only view of how DeltaGrid moves from a market hypothesis to evidence and a bounded decision.
            No public surface carries trading authority.
          </p>
        </div>
        <div className={styles.actions}>
          <Link href="/research">Demo workspace</Link>
          <Link href="/about">Access model</Link>
        </div>
      </header>

      <section className={styles.heroGrid} aria-label="Research falsification loop and current authority">
        <div className={styles.loopPanel}>
          <div className={styles.loopHeading}>
            <p>Research loop</p>
            <span>Hypothesis → evidence → bounded decision</span>
          </div>
          <ol className={styles.loopTrack}>
            {falsificationLoop.map(([index, label, description]) => (
              <li key={label}>
                <span className={styles.loopIndex}>{index}</span>
                <div>
                  <strong>{label}</strong>
                  <p>{description}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <aside className={styles.authorityPanel} aria-label="Current DeltaGrid authority">
          <div className={styles.authorityHeading}>
            <p>Current authority</p>
            <span>Research control · read-only observer</span>
          </div>
          <div className={styles.authorityGrid}>
            {statusTape.map(([label, value, tone]) => (
              <div className={styles.authorityCell} key={label}>
                <span>{label}</span>
                <strong className={tone === "blocked" ? styles.valueBlocked : styles.valueNeutral}>{value}</strong>
              </div>
            ))}
          </div>
          <p className={styles.authorityNote}>No broker connection · no order path · public authority effect: none.</p>
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
