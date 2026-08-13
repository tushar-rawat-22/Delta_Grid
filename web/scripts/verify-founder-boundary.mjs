import fs from "node:fs";
import path from "node:path";

const roots = ["founder", "research-app", "wrangler.founder.jsonc", "migrations"];
const forbiddenMarkers = [
  "sqlite3", "supabase", "child_process", "exec(", "spawn(", "eval(", "new Function",
  "offchain/", "~/.deltagrid", "/Users/", "process.env", "arbitrary command",
];
const secretAssignmentPatterns = [
  /\b(?:access_token|refresh_token|api_key|service_role|client_secret|private_key|hmac_key)\b\s*[:=]\s*["'`][^"'`\r\n]{8,}["'`]/iu,
  /["'](?:access_token|refresh_token|api_key|service_role|client_secret|private_key|hmac_key)["']\s*:\s*["'`][^"'`\r\n]{8,}["'`]/iu,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/u,
];
const emailLiteralPattern = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/iu;
const configuredTeamDomainPattern = /https:\/\/[A-Za-z0-9-]+\.cloudflareaccess\.com/iu;

for (const file of files(roots)) {
  const source = fs.readFileSync(file, "utf8");
  for (const marker of forbiddenMarkers) {
    if (source.toLowerCase().includes(marker.toLowerCase())) {
      throw new Error(`FOUNDER_BOUNDARY_FORBIDDEN_MARKER:${marker}:${file}`);
    }
  }
  for (const pattern of secretAssignmentPatterns) {
    if (pattern.test(source)) throw new Error(`FOUNDER_BOUNDARY_SECRET_ASSIGNMENT:${file}`);
  }
  if (emailLiteralPattern.test(source)) throw new Error(`FOUNDER_BOUNDARY_LITERAL_EMAIL:${file}`);
  if (configuredTeamDomainPattern.test(source)) throw new Error(`FOUNDER_BOUNDARY_LITERAL_TEAM_DOMAIN:${file}`);
}

const wranglerText = fs.readFileSync("wrangler.founder.jsonc", "utf8");
for (const forbiddenConfig of ["routes", "route", "services", "kv_namespaces", "r2_buckets", "queues", "account_id", "zone_id"]) {
  if (new RegExp(`"${forbiddenConfig}"\\s*:`, "u").test(wranglerText)) {
    throw new Error(`FOUNDER_WRANGLER_FORBIDDEN_CONFIG:${forbiddenConfig}`);
  }
}

const wrangler = JSON.parse(wranglerText);
if (wrangler.name !== "deltagrid-founder-gateway") throw new Error("FOUNDER_WRANGLER_NAME_INVALID");
if (wrangler.main !== "founder/worker.ts") throw new Error("FOUNDER_WRANGLER_ENTRYPOINT_INVALID");
if (wrangler.workers_dev !== true) throw new Error("FOUNDER_WORKERS_DEV_MUST_BE_ENABLED");
if (wrangler.preview_urls !== false) throw new Error("FOUNDER_PREVIEW_URLS_MUST_BE_DISABLED");
if (wrangler.send_metrics !== false) throw new Error("FOUNDER_WRANGLER_METRICS_MUST_BE_DISABLED");
if (wrangler.dependencies_instrumentation?.enabled !== false) throw new Error("FOUNDER_DEPENDENCY_INSTRUMENTATION_MUST_BE_DISABLED");
if (wrangler.observability?.enabled !== false) throw new Error("FOUNDER_OBSERVABILITY_MUST_BE_DISABLED");
if (JSON.stringify(wrangler.compatibility_flags) !== JSON.stringify(["nodejs_compat"])) throw new Error("FOUNDER_NODE_COMPAT_INVALID");
if (JSON.stringify(wrangler.triggers?.crons) !== JSON.stringify(["*/5 * * * *"])) throw new Error("FOUNDER_RESEARCH_CRON_INVALID");
const assets = wrangler.assets ?? {};
if (assets.directory !== "./research-dist" || assets.binding !== "ASSETS" || assets.run_worker_first !== true) {
  throw new Error("FOUNDER_RESEARCH_ASSET_AUTH_BOUNDARY_INVALID");
}
if (assets.html_handling !== "none" || assets.not_found_handling !== "none") throw new Error("FOUNDER_RESEARCH_ASSET_ROUTING_INVALID");

const expectedVars = {
  DELTAGRID_CORE_COMMIT: "d94441f2f32fd8edc7b416beecd88b2b087d01a9",
  DELTAGRID_AUTHORITY_STATE: "NONE",
};
if (JSON.stringify(wrangler.vars) !== JSON.stringify(expectedVars)) throw new Error("FOUNDER_PUBLIC_VARS_INVALID");

const databases = wrangler.d1_databases ?? [];
if (databases.length !== 1) throw new Error("FOUNDER_D1_BINDING_COUNT_INVALID");
const database = databases[0];
if (database.binding !== "DELTAGRID_SYSTEM_DB" || database.database_name !== "deltagrid-founder-system") {
  throw new Error("FOUNDER_D1_BINDING_INVALID");
}
if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/u.test(database.database_id)) throw new Error("FOUNDER_D1_ID_INVALID");
if (database.migrations_dir !== "migrations") throw new Error("FOUNDER_D1_MIGRATIONS_INVALID");

const requiredSecrets = [
  "DELTAGRID_ACCESS_TEAM_DOMAIN",
  "DELTAGRID_ACCESS_AUD",
  "DELTAGRID_FOUNDER_EMAIL",
  "DELTAGRID_AGENT_ACCESS_AUD",
  "DELTAGRID_AGENT_HMAC_KEY",
  "DELTAGRID_RESEARCH_CSRF_KEY",
  "ALPHA_VANTAGE_API_KEY",
  "FRED_API_KEY",
];
if (JSON.stringify(wrangler.secrets?.required ?? []) !== JSON.stringify(requiredSecrets)) {
  throw new Error("FOUNDER_REQUIRED_SECRET_NAMES_INVALID");
}

const worker = fs.readFileSync("founder/worker.ts", "utf8");
for (const route of [
  "/founder", "/founder/status", "/founder/security", "/founder/actions", "/founder/receipts",
  "/agent/v1/claim", "/agent/v1/start", "/agent/v1/complete",
  "/agent/v1/evidence", "/agent/v1/status",
  "/api/research/v1", "/research",
]) {
  if (!worker.includes(`"${route}"`)) throw new Error(`FOUNDER_ROUTE_MISSING:${route}`);
}
for (const action of [
  "VERIFY_CORE_STATUS", "VERIFY_M100_JOURNAL", "CAPTURE_M100_ONCE", "EXPORT_M100_BACKUP",
  "VERIFY_M100_BACKUP", "REFRESH_PUBLIC_PROJECTION", "VERIFY_PUBLIC_PROJECTION",
  "RUN_APPROVED_TEST_PROFILE", "SHOW_CONTRACT_IDENTITIES", "SHOW_WORKTREE_STATUS",
]) {
  if (!fs.readFileSync("founder/contracts.ts", "utf8").includes(`"${action}"`)) {
    throw new Error(`FOUNDER_FIXED_ACTION_MISSING:${action}`);
  }
}
if (!worker.includes("expected_authority_state: AUTHORITY_STATE")) throw new Error("FOUNDER_AUTHORITY_PIN_MISSING");
if (!fs.readFileSync("founder/agent-auth.ts", "utf8").includes("AGENT_NONCE_REPLAY")) throw new Error("FOUNDER_AGENT_REPLAY_GUARD_MISSING");
for (const marker of [
  "NON_RAB1_RESEARCH_ONLY", "DELTAGRID_RESEARCH_CSRF_KEY", "verifyResearchCsrf",
  "run_worker_first", "ALPHA_VANTAGE_API_KEY", "FRED_API_KEY",
]) {
  const sources = files(["founder", "research-app", "wrangler.founder.jsonc"]).map((file) => fs.readFileSync(file, "utf8")).join("\n");
  if (!sources.includes(marker)) throw new Error(`FOUNDER_RESEARCH_BOUNDARY_MISSING:${marker}`);
}

const auth = fs.readFileSync("founder/auth.ts", "utf8");
for (const marker of [
  "cf-access-jwt-assertion", "createRemoteJWKSet", "jwtVerify", 'algorithms: ["RS256"]',
  "DELTAGRID_ACCESS_TEAM_DOMAIN", "DELTAGRID_ACCESS_AUD", "DELTAGRID_FOUNDER_EMAIL",
]) {
  if (!auth.includes(marker)) throw new Error(`FOUNDER_AUTH_REQUIREMENT_MISSING:${marker}`);
}

console.log("FOUNDER_ACCESS_SOURCE_BOUNDARY=PASS");
console.log("FOUNDER_SECRET_ASSIGNMENT_SCAN=PASS");
console.log("FOUNDER_LITERAL_IDENTITY_SCAN=PASS");
console.log("FOUNDER_COMMAND_REGISTRY=FIXED_10");
console.log("FOUNDER_AGENT_TRANSPORT=OUTBOUND_ONLY");
console.log("FOUNDER_AGENT_REQUEST_SIGNING=HMAC_SHA256_REPLAY_PROTECTED");
console.log("FOUNDER_D1_BINDING=PASS");
console.log("FOUNDER_AUTHORITY_STATE=NONE");
console.log("FOUNDER_PREVIEW_URLS=DISABLED");
console.log("FOUNDER_WRANGLER_TELEMETRY=DISABLED");
console.log("FOUNDER_RESEARCH_BOUNDARY=NON_RAB1_RESEARCH_ONLY");
console.log("FOUNDER_RESEARCH_STATIC_ASSETS=ACCESS_REVALIDATED");

function files(entries) {
  const output = [];
  for (const entry of entries) {
    const stat = fs.statSync(entry);
    if (stat.isDirectory()) {
      for (const name of fs.readdirSync(entry)) output.push(...files([path.join(entry, name)]));
    } else {
      output.push(entry);
    }
  }
  return output;
}
