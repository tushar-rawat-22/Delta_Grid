import fs from "node:fs";

const policy = JSON.parse(
  fs.readFileSync(new URL("./dependency-policy.json", import.meta.url), "utf8"),
);
const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));

function sortedKeys(value) {
  return Object.keys(value ?? {}).sort();
}

function assertUnique(values, label) {
  if (new Set(values).size !== values.length) {
    throw new Error(`DEPENDENCY_POLICY_DUPLICATE:${label}`);
  }
}

for (const [section, allowedNames] of Object.entries(policy.directDependencies ?? {})) {
  assertUnique(allowedNames, section);
  const actualNames = sortedKeys(pkg[section]);
  const expectedNames = [...allowedNames].sort();
  if (JSON.stringify(actualNames) !== JSON.stringify(expectedNames)) {
    throw new Error(
      `DEPENDENCY_NAME_SET_MISMATCH:${section}:expected=${expectedNames.join(",")}:actual=${actualNames.join(",")}`,
    );
  }
}

const installScripts = policy.installScripts ?? [];
assertUnique(installScripts.map(({ name }) => name), "installScripts:name");
const expectedAllowScripts = Object.fromEntries(
  installScripts.map(({ name, version }) => [`${name}@${version}`, true]),
);
if (JSON.stringify(pkg.allowScripts ?? {}) !== JSON.stringify(expectedAllowScripts)) {
  throw new Error("INSTALL_SCRIPT_POLICY_MISMATCH");
}

const forbidden = [
  "@opennextjs/cloudflare", "@supabase/supabase-js", "next-auth", "@auth/core",
  "axios", "tailwindcss", "vitest", "jest", "tsx", "prettier", "hono", "express",
];
const all = { ...(pkg.dependencies ?? {}), ...(pkg.devDependencies ?? {}) };
for (const name of forbidden) {
  if (name in all) throw new Error(`FORBIDDEN_DIRECT_DEPENDENCY:${name}`);
}
for (const [name, version] of Object.entries(all)) {
  if (/^[~^*]|latest|next|workspace:|file:|git\+|https?:/u.test(String(version))) {
    throw new Error(`NON_EXACT_DIRECT_DEPENDENCY:${name}:${version}`);
  }
}

if (fs.existsSync("package-lock.json")) {
  const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
  if (lock.lockfileVersion !== 3) throw new Error("LOCKFILE_VERSION_INVALID");
  const root = lock.packages?.[""];
  if (!root) throw new Error("LOCKFILE_ROOT_MISSING");
  for (const section of Object.keys(policy.directDependencies ?? {})) {
    if (JSON.stringify(root[section] ?? {}) !== JSON.stringify(pkg[section] ?? {})) {
      throw new Error(`LOCKFILE_ROOT_MISMATCH:${section}`);
    }
  }

  const actualInstallScripts = [];
  for (const [lockPath, metadata] of Object.entries(lock.packages ?? {})) {
    if (!lockPath || metadata?.hasInstallScript !== true) continue;
    const marker = "node_modules/";
    const index = lockPath.lastIndexOf(marker);
    const name = index >= 0 ? lockPath.slice(index + marker.length) : null;
    if (!name || !metadata.version) {
      throw new Error(`INSTALL_SCRIPT_LOCK_ENTRY_INVALID:${lockPath}`);
    }
    actualInstallScripts.push(`${name}@${metadata.version}`);
  }
  actualInstallScripts.sort();
  const expectedInstallScripts = Object.keys(expectedAllowScripts).sort();
  if (JSON.stringify(actualInstallScripts) !== JSON.stringify(expectedInstallScripts)) {
    throw new Error(
      `INSTALL_SCRIPT_LOCK_SURFACE_MISMATCH:expected=${expectedInstallScripts.join(",")}:actual=${actualInstallScripts.join(",")}`,
    );
  }
}

console.log("DEPENDENCY_POLICY=PASS");
console.log("INSTALL_SCRIPT_POLICY=PASS");
console.log("LOCK_INSTALL_SCRIPT_SURFACE=PASS");
