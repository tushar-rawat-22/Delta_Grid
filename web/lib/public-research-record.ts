export const alphaSearchBRecord = {
  id: "alpha-search-b",
  label: "Alpha Search B",
  publicationCommit: "a31f4da4fc8b52ca2fa6aaad697350d6e9180736",
  publicationDateLabel: "18 Jul 2026",
  question: "Can public spot trade-flow survive realistic costs and falsification controls?",
  decision: "ALPHA_SEARCH_B_REJECTED_DEVELOPMENT",
  decisionLabel: "Rejected in development",
  candidateCount: 4,
  rejectedCandidateCount: 4,
  selectedCandidate: null,
  validationOpened: false,
  holdoutOpened: false,
  authorityEffect: "NONE",
  summary:
    "The protocol was frozen before evaluation. All four candidates failed the controlling development gates; validation and holdout remained sealed, and no candidate was selected.",
  lineage: [
    ["01", "Hypothesis", "Four candidates preregistered"],
    ["02", "Data", "Causally available public spot flow"],
    ["03", "Experiment", "Development split only"],
    ["04", "Costs", "Conservative scenario controlled"],
    ["05", "Falsification", "Null, Holm and replication checks"],
    ["06", "Evidence", "17 public source records preserved"],
    ["07", "Decision", "Rejected · no candidate advanced"],
  ],
  sourceRecords: [
    ["Protocol", "docs/ALPHA_SEARCH_B_PROTOCOL.md"],
    ["Development decision", "docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.md"],
    ["Protocol contract", "contracts/ALPHA_SEARCH_B_PROTOCOL_V1.json"],
    ["Cost-attribution contract", "contracts/ALPHA_SEARCH_B_COST_ATTRIBUTION_V1.json"],
    ["Candidate development results", "docs/evidence/alpha_search_b_development/CANDIDATE_DEVELOPMENT_RESULTS.json"],
    ["Cost attribution", "docs/evidence/alpha_search_b_development/COST_ATTRIBUTION.json"],
    ["Data acquisition manifest", "docs/evidence/alpha_search_b_development/DATA_ACQUISITION_MANIFEST.json"],
    ["Data certification", "docs/evidence/alpha_search_b_development/DATA_CERTIFICATION.json"],
    ["Machine development decision", "docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.json"],
    ["Feature-engine manifest", "docs/evidence/alpha_search_b_development/FEATURE_ENGINE_MANIFEST.json"],
    ["Holm adjustment", "docs/evidence/alpha_search_b_development/HOLM_ADJUSTMENT.json"],
    ["Null-control results", "docs/evidence/alpha_search_b_development/NULL_CONTROL_RESULTS.json"],
    ["P&L attribution", "docs/evidence/alpha_search_b_development/PNL_ATTRIBUTION.json"],
    ["Prohibited-access audit", "docs/evidence/alpha_search_b_development/PROHIBITED_ACCESS_AUDIT.json"],
    ["Replication results", "docs/evidence/alpha_search_b_development/REPLICATION_RESULTS.json"],
    ["Simulator manifest", "docs/evidence/alpha_search_b_development/SIMULATOR_MANIFEST.json"],
    ["Test results", "docs/evidence/alpha_search_b_development/TEST_RESULTS.json"],
  ],
} as const;

export function alphaSearchBSourceUrl(path: string) {
  return `https://github.com/tushar-rawat-22/Delta_Grid/blob/${alphaSearchBRecord.publicationCommit}/${path}`;
}
