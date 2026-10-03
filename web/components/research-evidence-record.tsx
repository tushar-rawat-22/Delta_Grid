import { alphaSearchBRecord, alphaSearchBSourceUrl } from "../lib/public-research-record";
import styles from "./research-evidence-record.module.css";

export function ResearchEvidenceRecord() {
  return (
    <section className={styles.record} id={alphaSearchBRecord.id} aria-labelledby="alpha-search-b-title">
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Preserved public research record</p>
          <h2 id="alpha-search-b-title">{alphaSearchBRecord.label}</h2>
          <p className={styles.question}>{alphaSearchBRecord.question}</p>
        </div>
        <div className={styles.decision}>
          <span>Controlling decision</span>
          <strong>{alphaSearchBRecord.decisionLabel}</strong>
        </div>
      </header>

      <div className={styles.body}>
        <div className={styles.lineagePanel}>
          <h3>Experiment lineage</h3>
          <ol className={styles.lineage}>
            {alphaSearchBRecord.lineage.map(([index, label, detail]) => (
              <li key={label}>
                <span>{index}</span>
                <div><strong>{label}</strong><p>{detail}</p></div>
              </li>
            ))}
          </ol>
        </div>

        <aside className={styles.finding} aria-labelledby="alpha-search-b-finding">
          <p className={styles.eyebrow}>Finding</p>
          <h3 id="alpha-search-b-finding">No candidate qualified.</h3>
          <p>{alphaSearchBRecord.summary}</p>
          <dl>
            <div><dt>Selected candidate</dt><dd>None</dd></div>
            <div><dt>Validation access</dt><dd>0</dd></div>
            <div><dt>Holdout access</dt><dd>0</dd></div>
            <div><dt>Authority effect</dt><dd>{alphaSearchBRecord.authorityEffect}</dd></div>
          </dl>
        </aside>
      </div>

      <div className={styles.sources}>
        <div className={styles.sourcesHeading}>
          <div>
            <p className={styles.eyebrow}>Evidence and provenance</p>
            <h3>{alphaSearchBRecord.sourceRecords.length} source records at the publication commit</h3>
          </div>
          <p>Published {alphaSearchBRecord.publicationDateLabel} · commit <code>{alphaSearchBRecord.publicationCommit.slice(0, 12)}</code></p>
        </div>
        <ul>
          {alphaSearchBRecord.sourceRecords.map(([label, path]) => (
            <li key={path}>
              <a href={alphaSearchBSourceUrl(path)} target="_blank" rel="noreferrer">
                <strong>{label}</strong>
                <span>{path}</span>
                <i aria-hidden="true">↗</i>
              </a>
            </li>
          ))}
        </ul>
      </div>

      <p className={styles.boundary}>
        This public record explains preserved development evidence. It does not reopen research, validate alpha,
        authorize protected-data access, or create paper-trading, live-trading, order or capital authority.
      </p>
    </section>
  );
}
