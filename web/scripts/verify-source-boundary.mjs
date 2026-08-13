import fs from "node:fs";
import path from "node:path";

const roots = ["app", "components", "lib"];
const files = [];
for (const root of roots) walk(root);
files.push("next.config.mjs", "wrangler.jsonc");

function walk(current) {
  for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
    const full = path.join(current, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (/\.(?:ts|tsx|js|mjs|jsonc)$/u.test(entry.name)) files.push(full);
  }
}

const forbidden = [
  [/@supabase|sqlite3|better-sqlite|service_role|api[_-]?key|access[_-]?token|refresh[_-]?token/iu, "secret_or_database_marker"],
  [/child_process|\bexec\s*\(|\bspawn\s*\(|eval\s*\(|new\s+Function\s*\(/u, "execution_surface"],
  [/\/Users\/|~\/\.deltagrid|governance\.sqlite3|acquisition\.sqlite3/iu, "private_runtime_path"],
  [/\bfetch\s*\(|axios|XMLHttpRequest|WebSocket\s*\(/u, "runtime_network_surface"],
  [/process\.env\.(?!NODE_ENV\b)/u, "runtime_environment_surface"],
];

for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  for (const [pattern, label] of forbidden) {
    if (pattern.test(text)) throw new Error(`FORBIDDEN_${label.toUpperCase()}:${file}`);
  }
}

const routeFiles = [
  "app/page.tsx", "app/markets/page.tsx", "app/research/page.tsx", "app/evidence/page.tsx",
  "app/missions/page.tsx", "app/system/page.tsx", "app/risk/page.tsx", "app/docs/page.tsx", "app/about/page.tsx",
];
for (const file of routeFiles) if (!fs.existsSync(file)) throw new Error(`ROUTE_MISSING:${file}`);
if (routeFiles.length !== 9) throw new Error("ROUTE_COUNT_INVALID");

const wrangler = fs.readFileSync("wrangler.jsonc", "utf8");
if (/"main"\s*:/u.test(wrangler) || /"binding"\s*:/u.test(wrangler)) throw new Error("WORKER_SERVER_SURFACE_FORBIDDEN");

console.log("STATIC_SOURCE_BOUNDARY=PASS");
console.log("PUBLIC_ROUTE_COUNT=9");
