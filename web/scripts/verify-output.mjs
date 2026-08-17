import fs from "node:fs";
import path from "node:path";

const root = "out";
if (!fs.existsSync(root)) throw new Error("STATIC_OUTPUT_MISSING");

const routes = ["", "markets", "research", "evidence", "missions", "system", "risk", "docs", "about"];
function routeFile(route) {
  if (route === "") return path.join(root, "index.html");
  const flat = path.join(root, `${route}.html`);
  if (fs.existsSync(flat)) return flat;
  return path.join(root, route, "index.html");
}
function routeExists(route) {
  return fs.existsSync(routeFile(route));
}
for (const route of routes) if (!routeExists(route)) throw new Error(`STATIC_ROUTE_MISSING:/${route}`);
if (!fs.existsSync(path.join(root, "404.html"))) throw new Error("STATIC_404_MISSING");
if (!fs.existsSync(path.join(root, "_headers"))) throw new Error("STATIC_HEADERS_MISSING");
if (!fs.existsSync(path.join(root, "robots.txt"))) throw new Error("ROBOTS_MISSING");
for (const snapshot of ["research-cockpit.png", "asset-dossier.png", "compare-macro.png"]) {
  const bytes = fs.readFileSync(path.join(root, "snapshots", snapshot));
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

const evidenceHtml = fs.readFileSync(routeFile("evidence"), "utf8");
for (const marker of [
  "Verified projection",
  "d94441f2f32fd8edc7b416beecd88b2b087d01a9",
  "0e13dae7cddddff1110d79630682bfbc1495f1bc23d5ea95cf15e2906fb967c4",
  "bf288d8b6349c2843b5196fa1857ae9c464773bbcf7cad9d821785ea67dfb6e8",
]) {
  if (!evidenceHtml.includes(marker)) throw new Error(`P1_3_EVIDENCE_OUTPUT_MISSING:${marker}`);
}

const overviewHtml = fs.readFileSync(routeFile(""), "utf8");
for (const marker of [
  "Mission 104",
  "NOT AUTHORIZED",
  "Verified projection",
  "A public view of a private research system.",
  "Founder only",
  "Log in",
  "no private or protected values",
]) {
  if (!overviewHtml.includes(marker)) throw new Error(`P1_3_OVERVIEW_OUTPUT_MISSING:${marker}`);
}

const researchHtml = fs.readFileSync(routeFile("research"), "utf8");
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

const headers = fs.readFileSync(path.join(root, "_headers"), "utf8");
for (const required of [
  "Content-Security-Policy:", "X-Content-Type-Options: nosniff", "X-Frame-Options: DENY",
  "Referrer-Policy: no-referrer", "Permissions-Policy:", "X-Robots-Tag: noindex, nofollow",
]) {
  if (!headers.includes(required)) throw new Error(`HEADER_POLICY_MISSING:${required}`);
}

const robots = fs.readFileSync(path.join(root, "robots.txt"), "utf8");
if (!robots.includes("User-agent: *") || !robots.includes("Allow: /") || robots.includes("Disallow: /")) {
  throw new Error("PUBLIC_ROBOTS_POLICY_INVALID");
}

console.log("STATIC_OUTPUT_INSPECTION=PASS");
console.log("P1_3_VERIFIED_PROJECTION_RENDER=PASS");
console.log("PUBLIC_ROUTE_COUNT=9");
console.log("PUBLIC_SANITIZED_PRODUCT_SNAPSHOTS=PASS");
console.log("PUBLIC_FOUNDER_LOGIN_RENDER=PASS");
console.log("PUBLIC_RESEARCH_DEMO_RENDER=PASS");
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
