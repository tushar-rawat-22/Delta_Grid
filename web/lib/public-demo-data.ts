export type DemoView =
  | "cockpit"
  | "intelligence"
  | "hypotheses"
  | "gates"
  | "trials"
  | "markets"
  | "compare"
  | "macro"
  | "notebook"
  | "health"
  | "system";

export const PUBLIC_DEMO_IDENTITY = {
  mode: "DEMO_MODE",
  provenance: "DEMO_FIXTURE",
  boundary: "PUBLIC_SANITIZED_RESEARCH_DEMO",
  authority_effect: "NONE",
  generated_label: "Deterministic fixture set · v1",
} as const;

export const DEMO_NAV: ReadonlyArray<{ id: DemoView; label: string; glyph: string }> = [
  { id: "cockpit", label: "Cockpit", glyph: "⌂" },
  { id: "intelligence", label: "Intelligence", glyph: "◈" },
  { id: "hypotheses", label: "Hypotheses", glyph: "◇" },
  { id: "gates", label: "Research gates", glyph: "⊢" },
  { id: "trials", label: "Trial ledger", glyph: "≣" },
  { id: "markets", label: "Markets", glyph: "◫" },
  { id: "compare", label: "Compare", glyph: "⇄" },
  { id: "macro", label: "Macro", glyph: "◎" },
  { id: "notebook", label: "Notebook", glyph: "✎" },
  { id: "health", label: "Data health", glyph: "◆" },
  { id: "system", label: "System boundary", glyph: "▣" },
] as const;

export const demoResearchGates = [
  { stage: "Strategy specification", state: "DEMO", detail: "Structured hypothesis and falsification fields are visible; no founder record is loaded." },
  { stage: "Dataset custody", state: "SANITIZED", detail: "Shows checksum/provenance concepts only. Private provider payloads and market values stay absent." },
  { stage: "Admission", state: "CLOSED", detail: "No canonical permit or protected-stage authorization is present in Demo Mode." },
  { stage: "Admission · repository", state: "UNAVAILABLE", detail: "Founder admission binds an exact repository commit and clean-state assertion. Demo Mode does not expose or bind a private worktree." },
  { stage: "Admission · dataset / split", state: "SANITIZED", detail: "The observer shows fixture identity and custody concepts only; protected, validation and holdout data remain unavailable and unopened." },
  { stage: "Admission · budget / control", state: "DEMO", detail: "Finite trial numbering and non-executing control concepts can be reviewed without reserving a real trial or consuming a canonical budget." },
  { stage: "Admission · decision", state: "CLOSED", detail: "No canonical admission decision, decision hash or permit exists here. Preflight visibility does not authorize execution or protected research." },
  { stage: "Trial reservation", state: "UNAVAILABLE", detail: "Append-only trial identity and finite-budget concepts are illustrated without persistence." },
  { stage: "Result bundle verification", state: "UNAVAILABLE", detail: "Founder research requires a canonical result bundle to pass identity, schema and integrity checks before application. Demo Mode loads no private result bundle." },
  { stage: "Deterministic engine application", state: "SIMULATED", detail: "The observer shows where a verified bundle would enter the deterministic application service without mutating founder registry, controls, evidence or runtime state." },
  { stage: "Engine decision output", state: "NO RESULT", detail: "No canonical result bundle is applied here, so the observer does not synthesize P&L, alpha, promotion or candidate state." },
  { stage: "Execution / accounting", state: "NOT AUTHORIZED", detail: "No paper/live engine, orders, capital, broker or exchange action can run from the observer." },
  { stage: "Statistical programme", state: "NO RESULT", detail: "No qualifying statistical result is available for promotion; the observer does not synthesize significance, alpha or profitability." },
  { stage: "Statistical programme · estimand", state: "LOCKED DEMO", detail: "The observer shows that the target quantity must be declared before results. The demo estimand is synthetic and cannot become founder evidence." },
  { stage: "Statistical programme · uncertainty", state: "NO RESULT", detail: "No canonical estimate, interval, standard error, p-value or posterior result exists in Demo Mode; uncertainty is never fabricated." },
  { stage: "Statistical programme · costs", state: "NO RESULT", detail: "No canonical gross or net result is available, so transaction-cost, slippage and financing sensitivity cannot be claimed as passed." },
  { stage: "Multiplicity review", state: "REQUIRED", detail: "A candidate decision must account for the declared finite search budget and multiple testing before any promotion claim." },
  { stage: "Robustness review", state: "NO RESULT", detail: "No protected split, sensitivity or robustness evidence is exposed or implied by deterministic demo fixtures." },
  { stage: "Candidate decision", state: "NONE", detail: "No strategy is selected. Software capability and green CI do not constitute research evidence or candidate admission." },
  { stage: "Protected opening · candidate", state: "NONE", detail: "A protected stage cannot open without a selected candidate. Current research state has no selected strategy to promote." },
  { stage: "Protected opening · evidence", state: "UNAVAILABLE", detail: "Validation, holdout and other protected evidence remain unopened and are never projected into the public observer." },
  { stage: "Protected opening · authorization", state: "ABSENT", detail: "No founder instruction authorizes RAB-1 / Mission 104 protected opening, permit use, paper/live execution or capital action." },
  { stage: "Protected opening", state: "CLOSED", detail: "RAB-1 / Mission 104 authority remains unopened under current governance." },
] as const;

export const demoStrategySpecification = [
  { field: "Research question", value: "Does a synthetic dispersion shock precede normalized volatility compression?", state: "DEMO", why: "Frames a falsifiable question without converting an observation into a signal." },
  { field: "Mechanism", value: "Predeclared fictional mean-reversion mechanism", state: "SANITIZED", why: "Explains the causal story that must survive evidence rather than being inferred after results." },
  { field: "Falsification rule", value: "Reject outside the fixed demo horizon", state: "LOCKED DEMO", why: "Makes failure observable before any trial result exists." },
  { field: "Search budget", value: "6 finite demo variants", state: "FINITE", why: "Bounds researcher degrees of freedom and feeds multiplicity review." },
  { field: "Dataset binding", value: "Unresolved until custody handoff", state: "UNAVAILABLE", why: "Prevents the public fixture from pretending a private canonical dataset is attached." },
  { field: "Execution authority", value: "None", state: "NOT AUTHORIZED", why: "A complete specification still cannot reserve a real trial, execute, trade or move capital." },
] as const;

export const demoTrialLedger = [
  { field: "Trial identity", value: "DEMO-TRIAL-000", status: "SIMULATED" },
  { field: "Variant budget", value: "Finite example", status: "DEMO" },
  { field: "Dataset binding", value: "Fixture checksum", status: "SANITIZED" },
  { field: "Code binding", value: "Deterministic demo revision", status: "SANITIZED" },
  { field: "Configuration binding", value: "Locked demo specification", status: "LOCKED DEMO" },
  { field: "Environment fingerprint", value: "Not projected publicly", status: "UNAVAILABLE" },
  { field: "Replay artifact", value: "No canonical replay artifact", status: "UNAVAILABLE" },
  { field: "Execution binding", value: "None", status: "NOT AUTHORIZED" },
  { field: "Accounting ledger", value: "No cash-flow records", status: "UNAVAILABLE" },
] as const;

export const demoDatasetCustody = [
  { binding: "Dataset identity", value: "DEMO-DATASET-001", state: "SANITIZED", evidence: "Deterministic fixture identity only; no founder dataset metadata." },
  { binding: "Content digest", value: "Demo digest placeholder", state: "SIMULATED", evidence: "Shows immutable-content binding without publishing a private or production checksum." },
  { binding: "Chronology", value: "Monotonic fixture timestamps", state: "VERIFIED DEMO", evidence: "Ordering is checked only inside the synthetic fixture set." },
  { binding: "Source rights", value: "DEMO_ONLY", state: "RESTRICTED", evidence: "No private provider payload, credential or redistributed vendor value is present." },
  { binding: "Custody receipt", value: "Unavailable publicly", state: "UNAVAILABLE", evidence: "Private operating receipts remain outside public Git and the observer." },
] as const;

export const demoOperatorWorkflow = [
  { lane: "Research intake", gate: "Specification", state: "DEMO", next: "Review mechanism, falsification and finite budget" },
  { lane: "Dataset custody", gate: "Provenance", state: "SANITIZED", next: "Verify checksum and chronology bindings" },
  { lane: "Trial execution", gate: "Admission + authority", state: "NOT AUTHORIZED", next: "No execution until canonical gates authorize it" },
  { lane: "Research engine", gate: "Verified result bundle", state: "NO RESULT", next: "Require a canonical verified bundle before deterministic state application" },
  { lane: "Candidate decision", gate: "Statistical programme", state: "NO RESULT", next: "Require estimand, uncertainty, costs, multiplicity and robustness evidence before promotion" },
  { lane: "Protected stage", gate: "RAB-1 / M104", state: "CLOSED", next: "Founder authorization remains absent" },
  { lane: "Public release", gate: "Exact revision + live marker", state: "UNVERIFIED", next: "Treat merge and green CI as insufficient until production reports the exact revision" },
  { lane: "Founder gateway", gate: "Authenticated identity boundary", state: "ACCESS CONTROLLED", next: "Keep anonymous founder APIs denied; use the private gateway only after intended authentication" },
] as const;

export const demoSystemBoundary = [
  { layer: "Public observer", state: "SANITIZED", detail: "Unauthenticated review surface. Deterministic fixtures only; no founder records or write path." },
  { layer: "Founder gateway", state: "ACCESS CONTROLLED", detail: "Private authenticated workspace boundary. The observer does not proxy or mirror private runtime payloads." },
  { layer: "Founder APIs", state: "DENIED ANONYMOUSLY", detail: "Private API capability remains outside the public observer and requires the intended founder identity boundary." },
  { layer: "Release provenance", state: "UNVERIFIED", detail: "A tested Git revision is not presented as deployed until the live release marker proves the exact production revision." },
  { layer: "Research authority", state: "NONE", detail: "Software visibility does not grant admission, protected opening, paper/live trading, credentials, orders or capital authority." },
  { layer: "Public interactions", state: "READ ONLY", detail: "Navigation and simulated workflow states are inspectable; executable founder actions remain disabled or unavailable." },
] as const;

export const demoWatchlist = [
  { symbol: "SYN-A", name: "Synthetic Growth Basket", index: 104.8, change: 1.6, state: "observed" },
  { symbol: "SYN-B", name: "Synthetic Defensive Basket", index: 98.7, change: -0.4, state: "observed" },
  { symbol: "SYN-C", name: "Synthetic Digital Basket", index: 111.2, change: 2.1, state: "observed" },
  { symbol: "SYN-D", name: "Synthetic Rates Basket", index: 101.5, change: 0.2, state: "observed" },
] as const;

export const demoTasks = [
  { title: "Review chronology assumption", type: "THESIS", status: "OPEN", due: "Demo queue" },
  { title: "Recheck transaction-cost sensitivity", type: "EVIDENCE", status: "OPEN", due: "Demo queue" },
  { title: "Document falsification boundary", type: "NOTE", status: "WATCHING", due: "Demo queue" },
] as const;

export const demoIntelligence = {
  breadth: { positive: 5, negative: 2, flat: 1, unavailable: 0 },
  risk: [
    { label: "Highest demo volatility", value: "SYN-C", note: "7-observation normalized window" },
    { label: "Deepest demo drawdown", value: "SYN-B", note: "-3.8% from fixture high" },
  ],
  priorities: [
    { kind: "VOLATILITY_REGIME", symbol: "SYN-C", metric: "7-observation volatility", value: "+18.4%", status: "QUESTION_ONLY" },
    { kind: "RELATIVE_WEAKNESS", symbol: "SYN-B", metric: "fixture drawdown", value: "-3.8%", status: "QUESTION_ONLY" },
  ],
} as const;

export const demoHypotheses = [
  {
    id: "DEMO-HYP-001",
    title: "Synthetic volatility compression after a dispersion shock",
    status: "DRAFT",
    revision: 3,
    mechanism: "A deliberately fictional mechanism used only to demonstrate the structured research workflow.",
    falsification: "Reject when the preregistered normalized spread fails to mean-revert inside the fixed demo horizon.",
    budget: "6 finite demo variants",
    bindings: "Dataset, permit, execution identity and statistical programme intentionally unresolved in Demo Mode.",
  },
  {
    id: "DEMO-HYP-002",
    title: "Synthetic cross-basket lead-lag persistence",
    status: "WATCHING",
    revision: 2,
    mechanism: "Illustrates how an observation can remain a question instead of becoming a trading signal.",
    falsification: "Reject when the relationship loses timestamp-aligned stability across the declared fixture windows.",
    budget: "4 finite demo variants",
    bindings: "No trial reservation, permit consumption, protected opening or execution side effect.",
  },
] as const;

export const demoMarketSeries = [
  { t: "T-6", a: 100.0, b: 100.0, c: 100.0 },
  { t: "T-5", a: 100.8, b: 99.6, c: 101.4 },
  { t: "T-4", a: 101.9, b: 99.2, c: 103.0 },
  { t: "T-3", a: 101.5, b: 98.8, c: 105.6 },
  { t: "T-2", a: 103.1, b: 99.0, c: 107.2 },
  { t: "T-1", a: 103.5, b: 98.4, c: 109.5 },
  { t: "T0", a: 104.8, b: 98.7, c: 111.2 },
] as const;

export const demoMacro = [
  { series: "Synthetic inflation pressure", latest: 102.4, previous: 102.1, unit: "normalized index", direction: "up" },
  { series: "Synthetic employment pressure", latest: 99.3, previous: 99.5, unit: "normalized index", direction: "down" },
  { series: "Synthetic policy pressure", latest: 101.0, previous: 101.0, unit: "normalized index", direction: "flat" },
  { series: "Synthetic liquidity pressure", latest: 103.2, previous: 102.7, unit: "normalized index", direction: "up" },
] as const;

export const demoNotebook = [
  { type: "THESIS", title: "Synthetic volatility compression", status: "DRAFT", revision: 3, updated: "Fixture revision 03" },
  { type: "EVIDENCE", title: "Chronology check example", status: "ACTIVE", revision: 2, updated: "Fixture revision 02" },
  { type: "RISK", title: "Cost sensitivity remains unresolved", status: "WATCHING", revision: 4, updated: "Fixture revision 04" },
  { type: "TASK", title: "Review preregistration handoff", status: "OPEN", revision: 1, updated: "Fixture revision 01" },
] as const;

export const demoHealth = [
  { provider: "Public crypto source", scope: "Synthetic digital mapping", status: "HEALTHY", freshness: "fixture current", rights: "DEMO_ONLY" },
  { provider: "Public equity source", scope: "Synthetic equity mapping", status: "HEALTHY", freshness: "fixture current", rights: "DEMO_ONLY" },
  { provider: "Public macro source", scope: "Synthetic macro mapping", status: "HEALTHY", freshness: "fixture current", rights: "DEMO_ONLY" },
  { provider: "Public company facts", scope: "Synthetic company mapping", status: "DEGRADED", freshness: "fixture delayed", rights: "DEMO_ONLY" },
] as const;

export function assertPublicDemoInvariants(): void {
  if (PUBLIC_DEMO_IDENTITY.mode !== "DEMO_MODE") throw new Error("PUBLIC_DEMO_MODE_INVALID");
  if (PUBLIC_DEMO_IDENTITY.provenance !== "DEMO_FIXTURE") throw new Error("PUBLIC_DEMO_PROVENANCE_INVALID");
  if (PUBLIC_DEMO_IDENTITY.authority_effect !== "NONE") throw new Error("PUBLIC_DEMO_AUTHORITY_INVALID");
  if (DEMO_NAV.length !== 11) throw new Error("PUBLIC_DEMO_NAV_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Admission · decision" && gate.state !== "CLOSED")) throw new Error("PUBLIC_DEMO_ADMISSION_DECISION_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Admission · repository" && gate.state !== "UNAVAILABLE")) throw new Error("PUBLIC_DEMO_ADMISSION_REPOSITORY_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Result bundle verification" && gate.state !== "UNAVAILABLE")) throw new Error("PUBLIC_DEMO_RESULT_BUNDLE_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Deterministic engine application" && gate.state !== "SIMULATED")) throw new Error("PUBLIC_DEMO_ENGINE_APPLICATION_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Engine decision output" && gate.state !== "NO RESULT")) throw new Error("PUBLIC_DEMO_ENGINE_RESULT_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Execution / accounting" && gate.state !== "NOT AUTHORIZED")) throw new Error("PUBLIC_DEMO_EXECUTION_AUTHORITY_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Statistical programme" && gate.state !== "NO RESULT")) throw new Error("PUBLIC_DEMO_RESULT_CLAIM_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Statistical programme · estimand" && gate.state !== "LOCKED DEMO")) throw new Error("PUBLIC_DEMO_ESTIMAND_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Statistical programme · uncertainty" && gate.state !== "NO RESULT")) throw new Error("PUBLIC_DEMO_UNCERTAINTY_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Statistical programme · costs" && gate.state !== "NO RESULT")) throw new Error("PUBLIC_DEMO_COST_REVIEW_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Multiplicity review" && gate.state !== "REQUIRED")) throw new Error("PUBLIC_DEMO_MULTIPLICITY_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Robustness review" && gate.state !== "NO RESULT")) throw new Error("PUBLIC_DEMO_ROBUSTNESS_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Candidate decision" && gate.state !== "NONE")) throw new Error("PUBLIC_DEMO_CANDIDATE_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Protected opening · candidate" && gate.state !== "NONE")) throw new Error("PUBLIC_DEMO_PROTECTED_CANDIDATE_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Protected opening · evidence" && gate.state !== "UNAVAILABLE")) throw new Error("PUBLIC_DEMO_PROTECTED_EVIDENCE_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Protected opening · authorization" && gate.state !== "ABSENT")) throw new Error("PUBLIC_DEMO_PROTECTED_AUTHORIZATION_INVALID");
  if (demoResearchGates.some((gate) => gate.stage === "Protected opening" && gate.state !== "CLOSED")) throw new Error("PUBLIC_DEMO_PROTECTED_OPENING_INVALID");
  if (demoStrategySpecification.some((item) => item.field === "Execution authority" && item.state !== "NOT AUTHORIZED")) throw new Error("PUBLIC_DEMO_STRATEGY_AUTHORITY_INVALID");
  if (demoStrategySpecification.some((item) => item.field === "Dataset binding" && item.state !== "UNAVAILABLE")) throw new Error("PUBLIC_DEMO_STRATEGY_DATASET_BINDING_INVALID");
  if (demoTrialLedger.some((item) => item.field === "Code binding" && item.status !== "SANITIZED")) throw new Error("PUBLIC_DEMO_REPLAY_CODE_BINDING_INVALID");
  if (demoTrialLedger.some((item) => item.field === "Configuration binding" && item.status !== "LOCKED DEMO")) throw new Error("PUBLIC_DEMO_REPLAY_CONFIG_BINDING_INVALID");
  if (demoTrialLedger.some((item) => item.field === "Environment fingerprint" && item.status !== "UNAVAILABLE")) throw new Error("PUBLIC_DEMO_REPLAY_ENVIRONMENT_INVALID");
  if (demoTrialLedger.some((item) => item.field === "Replay artifact" && item.status !== "UNAVAILABLE")) throw new Error("PUBLIC_DEMO_REPLAY_ARTIFACT_INVALID");
  if (demoDatasetCustody.some((item) => item.binding === "Custody receipt" && item.state !== "UNAVAILABLE")) throw new Error("PUBLIC_DEMO_CUSTODY_RECEIPT_INVALID");
  if (demoDatasetCustody.some((item) => item.binding === "Source rights" && item.value !== "DEMO_ONLY")) throw new Error("PUBLIC_DEMO_CUSTODY_RIGHTS_INVALID");
  if (demoOperatorWorkflow.some((item) => item.lane === "Trial execution" && item.state !== "NOT AUTHORIZED")) throw new Error("PUBLIC_DEMO_OPERATOR_EXECUTION_INVALID");
  if (demoOperatorWorkflow.some((item) => item.lane === "Research engine" && item.state !== "NO RESULT")) throw new Error("PUBLIC_DEMO_OPERATOR_ENGINE_INVALID");
  if (demoOperatorWorkflow.some((item) => item.lane === "Protected stage" && item.state !== "CLOSED")) throw new Error("PUBLIC_DEMO_OPERATOR_PROTECTED_STAGE_INVALID");
  if (demoOperatorWorkflow.some((item) => item.lane === "Public release" && item.state !== "UNVERIFIED")) throw new Error("PUBLIC_DEMO_OPERATOR_RELEASE_INVALID");
  if (demoOperatorWorkflow.some((item) => item.lane === "Founder gateway" && item.state !== "ACCESS CONTROLLED")) throw new Error("PUBLIC_DEMO_OPERATOR_FOUNDER_BOUNDARY_INVALID");
  if (demoSystemBoundary.some((item) => item.layer === "Release provenance" && item.state !== "UNVERIFIED")) throw new Error("PUBLIC_DEMO_RELEASE_PROVENANCE_INVALID");
  if (demoSystemBoundary.some((item) => item.layer === "Public interactions" && item.state !== "READ ONLY")) throw new Error("PUBLIC_DEMO_WRITE_BOUNDARY_INVALID");
}
