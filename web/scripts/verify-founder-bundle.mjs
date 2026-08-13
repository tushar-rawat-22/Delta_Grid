import fs from "node:fs";

const bundlePath = process.argv[2];
if (!bundlePath) throw new Error("FOUNDER_BUNDLE_PATH_REQUIRED");
if (!fs.existsSync(bundlePath)) throw new Error(`FOUNDER_BUNDLE_MISSING:${bundlePath}`);

const text = fs.readFileSync(bundlePath, "utf8");

const forbiddenRuntimeMarkers = [
  "governance.sqlite3",
  "acquisition.sqlite3",
  "~/.deltagrid",
  "/Users/",
  "forward_market_data",
  "research_custody",
  "mission101-research-reopening",
  "child_process",
  "eval(",
  "new Function(",
];

for (const marker of forbiddenRuntimeMarkers) {
  if (text.toLowerCase().includes(marker.toLowerCase())) {
    throw new Error(`FOUNDER_BUNDLE_PRIVATE_MARKER:${marker}`);
  }
}

const secretAssignmentPatterns = [
  /\b(?:access_token|refresh_token|api_key|service_role|client_secret)\b\s*[:=]\s*["'`][^"'`\r\n]{8,}["'`]/iu,
  /["'](?:access_token|refresh_token|api_key|service_role|client_secret)["']\s*:\s*["'`][^"'`\r\n]{8,}["'`]/iu,
  /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/u,
];
for (const pattern of secretAssignmentPatterns) {
  if (pattern.test(text)) throw new Error("FOUNDER_BUNDLE_SECRET_ASSIGNMENT");
}

const emailLiterals = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/giu) ?? [];
if (emailLiterals.length > 0) {
  throw new Error(`FOUNDER_BUNDLE_LITERAL_EMAIL:${emailLiterals[0]}`);
}

const concreteTeamDomains = text.match(/https:\/\/[A-Za-z0-9-]+\.cloudflareaccess\.com/giu) ?? [];
if (concreteTeamDomains.length > 0) {
  throw new Error(`FOUNDER_BUNDLE_LITERAL_TEAM_DOMAIN:${concreteTeamDomains[0]}`);
}

for (const required of [
  "cf-access-jwt-assertion",
  "RS256",
  "FOUNDER_ACCESS_IDENTITY_MISMATCH",
  "FOUNDER_ACCESS_TOKEN_MISSING",
  "AGENT_NONCE_REPLAY",
  "AGENT_SIGNATURE_INVALID",
  "DELTAGRID_AGENT_ACCESS_AUD",
  "requested_action_id",
  "expected_authority_state",
  "NON_RAB1_RESEARCH_ONLY",
  "RESEARCH_CSRF_KEY_INVALID",
  "PROVIDER_RESPONSE_TOO_LARGE",
  "ALPHA_VANTAGE_API_KEY",
  "FRED_API_KEY",
]) {
  if (!text.includes(required)) throw new Error(`FOUNDER_BUNDLE_AUTH_REQUIREMENT_MISSING:${required}`);
}

console.log("FOUNDER_WORKER_DRY_RUN_BUNDLE=PASS");
console.log("FOUNDER_BUNDLE_SECRET_ASSIGNMENT_SCAN=PASS");
console.log("FOUNDER_BUNDLE_LITERAL_IDENTITY_SCAN=PASS");
console.log("FOUNDER_BUNDLE_PRIVATE_RUNTIME_SCAN=PASS");
