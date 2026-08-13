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
      <section className="card-grid" aria-label={`${content.title} details`}>
        {content.cards.map((card) => <EvidenceCard key={card.title} card={card} />)}
      </section>
    </main>
  );
}
