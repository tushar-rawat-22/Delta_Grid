import fs from "node:fs";

const config = JSON.parse(fs.readFileSync("wrangler.jsonc", "utf8"));

if (config.name !== "deltagrid-observer") {
  throw new Error("PUBLIC_WORKER_NAME_INVALID");
}

if (!/^\d{4}-\d{2}-\d{2}$/u.test(config.compatibility_date ?? "")) {
  throw new Error("PUBLIC_COMPATIBILITY_DATE_INVALID");
}

const assets = config.assets;
if (!assets || assets.directory !== "./out") {
  throw new Error("PUBLIC_ASSET_DIRECTORY_INVALID");
}
if (assets.html_handling !== "auto-trailing-slash") {
  throw new Error("PUBLIC_HTML_HANDLING_INVALID");
}
if (assets.not_found_handling !== "404-page") {
  throw new Error("PUBLIC_NOT_FOUND_HANDLING_INVALID");
}

const forbiddenTopLevel = [
  "main",
  "vars",
  "d1_databases",
  "kv_namespaces",
  "r2_buckets",
  "durable_objects",
  "services",
  "queues",
  "triggers",
  "hyperdrive",
  "vectorize",
  "ai",
  "browser",
  "mtls_certificates",
];

for (const key of forbiddenTopLevel) {
  if (Object.hasOwn(config, key)) {
    throw new Error(`PUBLIC_RUNTIME_SURFACE_FORBIDDEN:${key}`);
  }
}

if (Object.hasOwn(assets, "binding") || Object.hasOwn(assets, "run_worker_first")) {
  throw new Error("PUBLIC_ASSET_BINDING_FORBIDDEN");
}

const headers = fs.readFileSync("public/_headers", "utf8");
const globalHeaders = headers.split(/\n\s*\n/u, 1)[0];
const requiredSecurityHeaders = [
  "X-Content-Type-Options: nosniff",
  "X-Frame-Options: DENY",
  "Referrer-Policy: no-referrer",
  "Permissions-Policy:",
  "Cross-Origin-Opener-Policy: same-origin",
  "Cross-Origin-Resource-Policy: same-origin",
  "Content-Security-Policy:",
];

for (const header of requiredSecurityHeaders) {
  if (!globalHeaders.includes(header)) {
    throw new Error(`PUBLIC_SECURITY_HEADER_MISSING:${header.split(":", 1)[0]}`);
  }
}

if (/X-Robots-Tag:/iu.test(globalHeaders)) {
  throw new Error("PUBLIC_GLOBAL_NOINDEX_FORBIDDEN");
}

const bootstrapNoindex = [
  "https://deltagrid-observer.tushar142004.workers.dev/*",
  "  X-Robots-Tag: noindex, nofollow",
].join("\n");
if (!headers.includes(bootstrapNoindex)) {
  throw new Error("PUBLIC_BOOTSTRAP_NOINDEX_MISSING");
}

console.log("PUBLIC_DEPLOY_CONFIG=PASS");
console.log("PUBLIC_WORKER=deltagrid-observer");
console.log("PUBLIC_RUNTIME=STATIC_ASSETS_ONLY");
console.log("PUBLIC_STATEFUL_BINDINGS=0");
console.log("PUBLIC_SECURITY_HEADERS=PASS");
console.log("PUBLIC_BOOTSTRAP_INDEXING=NOINDEX_ONLY_ON_WORKERS_DEV");
