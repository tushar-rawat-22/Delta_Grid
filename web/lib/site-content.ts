import {
  currentProjection,
  P1_CORE_COMMIT,
  P1_PROJECTION_SHA256,
  projectionAuthority,
  requireClosedAuthority,
  requireNoCapitalAuthority,
  verifiedProjectionSource,
} from "./current-projection.ts";
import type { Provenance } from "./projection/provenance.ts";

export type StatusItem = {
  label: string;
  value: string;
  provenance: Provenance;
  source?: string;
};

export type PageCard = {
  title: string;
  body: string;
  provenance: Provenance;
  source?: string;
};

export type ObserverPageContent = {
  eyebrow: string;
  title: string;
  summary: string;
  cards: PageCard[];
};

export const CORE_COMMIT = P1_CORE_COMMIT;
export const PUBLIC_SOURCE = `Delta_Grid public repository @ ${CORE_COMMIT.slice(0, 12)}`;
export const VERIFIED_PROJECTION_SOURCE = verifiedProjectionSource;

const projectionContract = currentProjection.projection.contract_identities.find(
  (item) => item.contract_id === "deltagrid-public-projection-v1",
);
if (!projectionContract) throw new Error("P1_3_PUBLIC_PROJECTION_CONTRACT_IDENTITY_MISSING");

export const statusItems: StatusItem[] = [
  {
    label: "Validated alpha",
    value: "NONE",
    provenance: "PUBLIC_DOCUMENT_DERIVED",
    source: `${PUBLIC_SOURCE} · README.md`,
  },
  {
    label: "Selected candidate",
    value: "NONE",
    provenance: "PUBLIC_DOCUMENT_DERIVED",
    source: `${PUBLIC_SOURCE} · README.md`,
  },
  {
    label: "Mission 104",
    value: requireClosedAuthority("m104_observation"),
    provenance: "VERIFIED_P1_PROJECTION",
    source: VERIFIED_PROJECTION_SOURCE,
  },
  {
    label: "Paper trading",
    value: requireClosedAuthority("paper_trading"),
    provenance: "VERIFIED_P1_PROJECTION",
    source: VERIFIED_PROJECTION_SOURCE,
  },
  {
    label: "Live trading",
    value: requireClosedAuthority("live_trading"),
    provenance: "VERIFIED_P1_PROJECTION",
    source: VERIFIED_PROJECTION_SOURCE,
  },
  {
    label: "Capital authority",
    value: requireNoCapitalAuthority(),
    provenance: "VERIFIED_P1_PROJECTION",
    source: VERIFIED_PROJECTION_SOURCE,
  },
];

export const pageContent: Record<string, ObserverPageContent> = {
  overview: {
    eyebrow: "Public observer",
    title: "What DeltaGrid can prove right now",
    summary:
      "This site shows a small, verified slice of DeltaGrid's public state. It does not run research, connect to trading accounts, or grant authority back to the core system.",
    cards: [
      {
        title: "Current authority",
        body: `The admitted package binds core commit ${P1_CORE_COMMIT} to projection SHA-256 ${P1_PROJECTION_SHA256}. Mission 104 observation, paper trading, live trading, credentials, orders, allocation, and capital deployment are all false in that package.`,
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
      {
        title: "Research result",
        body: "The public repository currently records no validated profitable strategy and no selected candidate. Those statements are document-derived because the sealed public projection deliberately contains no alpha or candidate fields.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
      {
        title: "Why the site stays separate",
        body: "The observer is static and has no database, private runtime mount, API command route, credential path, or generic executor. A web failure cannot turn into DeltaGrid authority.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: "Public observer architecture",
      },
    ],
  },
  markets: {
    eyebrow: "Markets",
    title: "Market values are not published here",
    summary:
      "The admitted package contains repository, authority, contract, and public-document identities. It does not contain prices, funding values, protected data, or private runtime state.",
    cards: [
      {
        title: "Prices and funding",
        body: "Not part of the current public projection.",
        provenance: "NOT_PUBLICLY_PROJECTED",
      },
      {
        title: "Data rights",
        body: "Vendor or provider values will not be displayed until their redistribution rights and public-display rules have been reviewed and a projection source has been approved.",
        provenance: "NOT_PUBLICLY_PROJECTED",
      },
      {
        title: "Private custody",
        body: "The verified package contains no market values and creates no route into Mission 100 or Mission 101 private custody and runtime state.",
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
    ],
  },
  research: {
    eyebrow: "Research",
    title: "Rejected work stays in the record",
    summary:
      "DeltaGrid keeps failed and weak hypotheses visible. The project is not a dashboard that hides everything except its best-looking backtest.",
    cards: [
      {
        title: "Funding and basis carry",
        body: "Rejected in the recorded research programme.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
      {
        title: "Directional strategies",
        body: "Rejected during development. No candidate was promoted.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
      {
        title: "Macro, trade-flow and lead-lag work",
        body: "These hypotheses were rejected or stopped before a promotable candidate emerged. Alpha Search B was rejected on development data without opening validation or holdout data.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
    ],
  },
  evidence: {
    eyebrow: "Evidence",
    title: "The public package is reproduced before it is trusted",
    summary:
      "CI regenerates the package from the exact public-core commit and compares the resulting files byte for byte with the copy used by this site.",
    cards: [
      {
        title: "Admitted projection",
        body: `Core commit ${P1_CORE_COMMIT}; projection SHA-256 ${P1_PROJECTION_SHA256}; contract hash ${projectionContract.contract_hash_sha256}.`,
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
      {
        title: "Production governance registries",
        body: `Statistical adapters: ${projectionAuthority.production_statistical_adapter_count}. Protected evaluators: ${projectionAuthority.production_protected_evaluator_count}.`,
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
      {
        title: "What the hash proves",
        body: "The current checks establish reproducibility and integrity through an exact core checkout, the Python exporter, an independent TypeScript verifier, SHA-256 binding, and byte parity. DeltaGrid does not claim a detached publisher signature yet.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: "Public projection provenance policy",
      },
    ],
  },
  missions: {
    eyebrow: "Mission history",
    title: "Building a component does not authorize its next stage",
    summary:
      "Recent missions added custody, research, execution, and statistical controls in small steps. Each stage remains separately gated.",
    cards: [
      {
        title: "Missions 93–97",
        body: "Added bounded admission, result verification, read-only projection and cockpit work, plus durable observation infrastructure.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
      {
        title: "Missions 98–103",
        body: "Added decision-only research direction, temporal custody, bounded acquisition, development admission and execution, and finite-program statistical governance. No production candidate was created.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
      {
        title: "Mission 104",
        body: `Observation remains false in the admitted authority projection. The contract defines ${projectionAuthority.maximum_verdict} as its maximum verdict label, with authority effect ${projectionAuthority.maximum_verdict_authority_effect}; that label does not mean any current candidate has achieved the verdict.`,
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
    ],
  },
  system: {
    eyebrow: "System",
    title: "The public site is downstream of the core",
    summary:
      "DeltaGrid core remains authoritative. The web layer renders a verified snapshot and has no path for rewriting research evidence or governance state.",
    cards: [
      {
        title: "Build source",
        body: `The current snapshot was reproduced from Delta_Grid commit ${P1_CORE_COMMIT} and independently verified at SHA-256 ${P1_PROJECTION_SHA256}.`,
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
      {
        title: "Static public deployment",
        body: "Next.js exports the public site to static files. Cloudflare Workers Static Assets can serve those files without a public application server.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: "Public observer architecture",
      },
      {
        title: "Snapshot freshness",
        body: "The package is verified for one exact core commit. If the core advances, the old package stays historically valid but is not presented as the new core until another admission is completed.",
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
    ],
  },
  risk: {
    eyebrow: "Risk",
    title: "Unclear authority stays closed",
    summary:
      "The observer does not fill gaps with guesses. It distinguishes verified projection fields, public-document statements, and state that is deliberately not published.",
    cards: [
      {
        title: "Built does not mean authorized",
        body: "Infrastructure can exist while the research or trading stage that might use it remains closed.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
      {
        title: "Operational authority",
        body: "Model/ML, Mission 104 observation, paper/live trading, exchange account access, credentials, signed requests, orders, portfolio allocation, capital deployment, and self-authorization are all false in the projection.",
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
      {
        title: "A verdict label is not deployment",
        body: `The contract's maximum verdict label is ${projectionAuthority.maximum_verdict} with authority effect ${projectionAuthority.maximum_verdict_authority_effect}. It cannot place an order and does not prove that a current candidate is qualified.`,
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
    ],
  },
  docs: {
    eyebrow: "Verification index",
    title: "Three documents define the public boundary.",
    summary:
      "Each document is identified by its repository path and exact SHA-256 digest. The interface separates cryptographically verified fields from statements summarized from public documents.",
    cards: currentProjection.projection.public_document_identities
      .filter((item) => item.path !== "README.md")
      .map((item) => ({
        title: item.path.split("/").at(-1) ?? item.path,
        body: `Repository path: ${item.path}. Content digest: ${item.sha256}.`,
        provenance: "VERIFIED_P1_PROJECTION" as const,
        source: VERIFIED_PROJECTION_SOURCE,
      })),
  },
  about: {
    eyebrow: "About",
    title: "DeltaGrid is a research system, not a return claim",
    summary:
      "The project tests quantitative hypotheses under chronology, cost, data-custody, statistical, and authority constraints, and keeps rejected evidence in the record.",
    cards: [
      {
        title: "Purpose",
        body: "Test falsifiable market hypotheses under realistic constraints and preserve weak or negative results instead of promoting them early.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
      {
        title: "Public repository",
        body: "The core repository is visible for portfolio demonstration, inspection, and professional review under its stated license terms.",
        provenance: "PUBLIC_DOCUMENT_DERIVED",
        source: `${PUBLIC_SOURCE} · README.md`,
      },
      {
        title: "Observer authority",
        body: "NONE. The admitted package requires the operational and trading authority flags it projects to remain false, and the website has no control path back into DeltaGrid.",
        provenance: "VERIFIED_P1_PROJECTION",
        source: VERIFIED_PROJECTION_SOURCE,
      },
    ],
  },
};
