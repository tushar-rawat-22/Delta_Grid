import fs from "node:fs";
import path from "node:path";

const root = "out";
try {
  fs.readdirSync(root);
} catch (error) {
  if (error?.code === "ENOENT") throw new Error("STATIC_OUTPUT_MISSING");
  throw error;
}

const routes = ["", "markets", "research", "evidence", "missions", "system", "risk", "docs", "about"];

function readRoute(route) {
  const candidates = route === ""
    ? [path.join(root, "index.html")]
    : [path.join(root, `${route}.html`), path.join(root, route, "index.html")];

  for (const file of candidates) {
    try {
      return { file, text: fs.readFileSync(file, "utf8") };
    } catch (error) {
      if (error?.code === "ENOENT") continue;
      throw error;
    }
  }

  throw new Error(`STATIC_ROUTE_MISSING:/${route}`);
}

function readRequiredText(file, missingCode) {
  try {
    return fs.readFileSync(file, "utf8");
  } catch (error) {
    if (error?.code === "ENOENT") throw new Error(missingCode);
    throw error;
  }
}

function readRequiredBytes(file, missingCode) {
  try {
    return fs.readFileSync(file);
  } catch (error) {
    if (error?.code === "ENOENT") throw new Error(missingCode);
    throw error;
  }
}

const routeOutput = new Map(routes.map((route) => [route, readRoute(route)]));
readRequiredText(path.join(root, "404.html"), "STATIC_404_MISSING");
const headers = readRequiredText(path.join(root, "_headers"), "STATIC_HEADERS_MISSING");
const robots = readRequiredText(path.join(root, "robots.txt"), "ROBOTS_MISSING");

for (const snapshot of ["research-cockpit.png", "asset-dossier.png", "compare-macro.png"]) {
  const bytes = readRequiredBytes(
    path.join(root, "snapshots", snapshot),
    `SANITIZED_SNAPSHOT_INVALID:${snapshot}`,
  );
  if (bytes.length < 10_000 || bytes.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a") {
    throw new Error(`SANITIZED_SNAPSHOT_INVALID:${snapshot}`);
  }
}

const forbiddenMarkers = [
  "/Users/", "~/.deltagrid", "governance.sqlite3", "acquisition.sqlite3",
  "service_role", "api_key", "access_token", "refresh_token", "founder_nonce",
];
const externalAsset = /<(?:script|img|link)\b[^>]*(?:src|href)=["']https?:\/\//iu;
const externalCss = /url\(\s*["']?https?:\/\//iu;

for (const file of allFiles(root)) {
  if (!/\.(?:html|css|js|json|txt)$/u.test(file)) continue;
  const text = fs.readFileSync(file, "utf8");
  for (const marker of forbiddenMarkers) {
    if (text.toLowerCase().includes(marker.toLowerCase())) throw new Error(`FORBIDDEN_OUTPUT_MARKER:${marker}:${file}`);
  }
  if (file.endsWith(".html") && externalAsset.test(text)) throw new Error(`EXTERNAL_HTML_ASSET:${file}`);
  if (file.endsWith(".css") && externalCss.test(text)) throw new Error(`EXTERNAL_CSS_ASSET:${file}`);
}

for (const route of routes) {
  const html = routeOutput.get(route).text;
  for (const marker of ["Public demo", "Open Demo", "Founder Log in", "Demo Mode", "Sanitized fixtures · no writes"]) {
    if (!html.includes(marker)) throw new Error(`PUBLIC_SHELL_OUTPUT_MISSING:${marker}:/${route}`);
  }
}

const evidenceHtml = routeOutput.get("evidence").text;
for (const marker of [
  "Verified projection",
  "d94441f2f32fd8edc7b416beecd88b2b087d01a9",
  "0e13dae7cddddff1110d79630682bfbc1495f1bc23d5ea95cf15e2906fb967c4",
  "bf288d8b6349c2843b5196fa1857ae9c464773bbcf7cad9d821785ea67dfb6e8",
]) {
  if (!evidenceHtml.includes(marker)) throw new Error(`P1_3_EVIDENCE_OUTPUT_MISSING:${marker}`);
}

const overviewHtml = routeOutput.get("").text;
for (const marker of [
  "DeltaGrid / public research observer",
  "Research control",
  "Research result",
  "No validated alpha",
  "Selected candidate",
  "None selected",
  "Paper / live",
  "Disabled",
  "Capital",
  "Blocked",
  "Mission 104",
  "Candidate observation",
  "NOT AUTHORIZED",
  "Demo workspace",
  "Founder access",
  "Public inputs",
  "Public / founder separation",
  "Broker connection",
  "Exchange credentials",
  "Orders",
  "Portfolio allocation",
  "Public write path",
  "authority effect NONE",
]) {
  if (!overviewHtml.includes(marker)) throw new Error(`P1_3_OVERVIEW_OUTPUT_MISSING:${marker}`);
}

const researchHtml = routeOutput.get("research").text;
for (const marker of [
  "DEMO MODE",
  "SANITIZED FIXTURES",
  "NOT LIVE",
  "NO WRITES",
  "Log in for Founder Mode",
  "Cockpit",
  "Intelligence",
  "Hypotheses",
  "Markets",
  "Compare",
  "Macro",
  "Notebook",
  "Data health",
  "AUTHORITY NONE",
]) {
  if (!researchHtml.includes(marker)) throw new Error(`PUBLIC_DEMO_OUTPUT_MISSING:${marker}`);
}

for (const required of [
  "Content-Security-Policy:", "X-Content-Type-Options: nosniff", "X-Frame-Options: DENY",
  "Referrer-Policy: no-referrer", "Permissions-Policy:", "X-Robots-Tag: noindex, nofollow",
]) {
  if (!headers.includes(required)) throw new Error(`HEADER_POLICY_MISSING:${required}`);
}

if (!robots.includes("User-agent: *") || !robots.includes("Allow: /") || robots.includes("Disallow: /")) {
  throw new Error("PUBLIC_ROBOTS_POLICY_INVALID");
}

console.log("STATIC_OUTPUT_INSPECTION=PASS");
console.log("P1_3_VERIFIED_PROJECTION_RENDER=PASS");
console.log("PUBLIC_ROUTE_COUNT=9");
console.log("PUBLIC_SANITIZED_PRODUCT_SNAPSHOTS=PASS");
console.log("PUBLIC_FOUNDER_LOGIN_RENDER=PASS");
console.log("PUBLIC_RESEARCH_DEMO_RENDER=PASS");
console.log("PUBLIC_DEMO_PRIMARY_ENTRY=PASS");
console.log("PUBLIC_UNIFIED_SHELL_RENDER=PASS");
console.log("PUBLIC_CRAWL_POLICY=PASS");

function allFiles(current) {
  const output = [];
  for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
    const full = path.join(current, entry.name);
    if (entry.isDirectory()) output.push(...allFiles(full));
    else output.push(full);
  }
  return output;
}
