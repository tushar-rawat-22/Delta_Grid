import type { PageCard } from "../lib/site-content";
import { ProvenanceBadge } from "./provenance-badge";

export function EvidenceCard({ card }: { card: PageCard }) {
  return (
    <article className="card">
      <div className="card-topline">
        <h2>{card.title}</h2>
        <ProvenanceBadge value={card.provenance} />
      </div>
      <p>{card.body}</p>
      {card.source ? <p className="source">Source: {card.source}</p> : null}
    </article>
  );
}
