import type { Provenance } from "../lib/projection/provenance";

const labels: Record<Provenance, string> = {
  VERIFIED_P1_PROJECTION: "Verified projection",
  PUBLIC_DOCUMENT_DERIVED: "Public source",
  DEMO_FIXTURE: "Demo fixture",
  NOT_PUBLICLY_PROJECTED: "Not projected",
};

export function ProvenanceBadge({ value }: { value: Provenance }) {
  return <span className={`provenance provenance-${value.toLowerCase()}`}>{labels[value]}</span>;
}
