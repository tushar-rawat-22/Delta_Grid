import fs from "node:fs";

const expected = {
  dependencies: {
    jose: "6.2.9",
    next: "16.3.1",
    react: "19.2.8",
    "react-dom": "19.2.8",
  },
  devDependencies: {
    "@types/node": "24.13.3",
    "@types/react": "19.2.18",
    "@types/react-dom": "19.2.4",
    "@vitejs/plugin-react": "6.1.0",
    eslint: "9.39.5",
    "eslint-config-next": "16.3.1",
    typescript: "6.0.3",
    vite: "8.2.2",
    wrangler: "4.125.0",
  },
};

const expectedAllowScripts = {
  "esbuild@0.28.1": true,
  "fsevents@2.3.3": true,
  "unrs-resolver@1.12.2": true,
  "workerd@1.20260820.1": true,
};

const pkg = JSON.parse(fs.readFileSync("package.json", "utf8"));
for (const section of Object.keys(expected)) {
  const actual = pkg[section] ?? {};
  const wanted = expected[section];
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    throw new Error(`DEPENDENCY_SET_MISMATCH:${section}`);
  }
}
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
  for (const section of Object.keys(expected)) {
    if (JSON.stringify(root[section] ?? {}) !== JSON.stringify(expected[section])) {
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
