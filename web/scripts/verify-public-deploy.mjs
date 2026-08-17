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

console.log("PUBLIC_DEPLOY_CONFIG=PASS");
console.log("PUBLIC_WORKER=deltagrid-observer");
console.log("PUBLIC_RUNTIME=STATIC_ASSETS_ONLY");
console.log("PUBLIC_STATEFUL_BINDINGS=0");
