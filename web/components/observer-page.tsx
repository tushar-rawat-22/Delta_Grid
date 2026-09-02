import { pageContent } from "../lib/site-content";
import { EvidenceCard } from "./evidence-card";
import { StatusStrip } from "./status-strip";

const titleToPage = {
  Overview: "overview",
  Markets: "markets",
  Research: "research",
  Evidence: "evidence",
  Missions: "missions",
  System: "system",
  Risk: "risk",
  Docs: "docs",
  About: "about",
} as const;

const observerBoundary = [
  {
    label: "Data boundary",
    value: "SANITIZED",
    detail: "Public-contract state and deterministic fixtures only. No founder records, protected evidence, private runtime payloads or real private market values.",
  },
  {
    label: "Interaction boundary",
    value: "READ ONLY",
    detail: "Founder actions are represented as disabled or simulated workflow states. This surface cannot reserve trials, issue permits, write evidence, trade or move capital.",
  },
  {
    label: "Research authority",
    value: "NONE",
    detail: "No validated profitable strategy or selected candidate is implied. Protected opening, paper/live trading, credentials, orders, leverage and allocation remain unauthorized.",
  },
  {
    label: "Identity model",
    value: "TWO LAYERS",
    detail: "Live release provenance identifies the deployed website revision. Research provenance identifies the separately admitted core snapshot used by the public projection. Those revisions can differ without making either claim stale or unverified.",
  },
] as const;

const unverifiedReleaseDetail =
  "This build has not been bound to a verified live release. Production deployment must prove the exact deployed revision before this status changes.";

type ObserverPageProps = {
  title: keyof typeof titleToPage;
  purpose?: string;
};

export function ObserverPage({ title }: ObserverPageProps) {
  const page = titleToPage[title];
  const content = pageContent[page];
  return (
    <main>
      <section className="hero">
        <p className="eyebrow">{content.eyebrow}</p>
        <h1>{content.title}</h1>
        <p className="lede">{content.summary}</p>
      </section>
      {page === "overview" ? <StatusStrip /> : null}
      <section className="card-grid" aria-label="Public observer operating boundary">
        {observerBoundary.map((item) => (
          <article className="card" key={item.label}>
            <div className="card-topline">
              <h2>{item.label}</h2>
              <span className="badge">{item.value}</span>
            </div>
            <p>{item.detail}</p>
          </article>
        ))}
        <article className="card" data-release-provenance="UNVERIFIED">
          <div className="card-topline">
            <h2>Release provenance</h2>
            <span className="badge" data-release-provenance-status="UNVERIFIED">UNVERIFIED</span>
          </div>
          <p data-release-provenance-detail="UNVERIFIED">{unverifiedReleaseDetail}</p>
        </article>
      </section>
      <section className="card-grid" aria-label={`${content.title} details`}>
        {content.cards.map((card) => <EvidenceCard key={card.title} card={card} />)}
      </section>
    </main>
  );
}
