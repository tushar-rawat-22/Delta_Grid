import { statusItems } from "../lib/site-content";
import { ProvenanceBadge } from "./provenance-badge";

export function StatusStrip() {
  return (
    <section className="status-grid" aria-label="Current public status">
      {statusItems.map((item) => (
        <article className="status-item" key={item.label}>
          <div className="status-label">{item.label}</div>
          <strong>{item.value}</strong>
          <ProvenanceBadge value={item.provenance} />
        </article>
      ))}
    </section>
  );
}
