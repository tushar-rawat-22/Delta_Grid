import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const approvedInstallScripts = new Map([
  ["esbuild", "0.28.1"],
  ["fsevents", "2.3.3"],
  ["unrs-resolver", "1.12.2"],
  ["workerd", "1.20260804.1"],
]);
const optionalOnThisPlatform = new Set(["fsevents"]);

function run(command, args) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    env: process.env,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`COMMAND_FAILED:${command}:${args.join(" ")}:${result.status}`);
  }
}

function packageNameFromLockPath(lockPath) {
  const marker = "node_modules/";
  const index = lockPath.lastIndexOf(marker);
  if (index < 0) return null;
  return lockPath.slice(index + marker.length);
}

const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
const actualScriptPackages = [];
for (const [lockPath, metadata] of Object.entries(lock.packages ?? {})) {
  if (!lockPath || metadata?.hasInstallScript !== true) continue;
  const name = packageNameFromLockPath(lockPath);
  if (!name || !metadata.version) {
    throw new Error(`INSTALL_SCRIPT_LOCK_ENTRY_INVALID:${lockPath}`);
  }
  actualScriptPackages.push(`${name}@${metadata.version}`);
}
actualScriptPackages.sort();

const expectedScriptPackages = [...approvedInstallScripts]
  .map(([name, version]) => `${name}@${version}`)
  .sort();

if (JSON.stringify(actualScriptPackages) !== JSON.stringify(expectedScriptPackages)) {
  throw new Error(
    `INSTALL_SCRIPT_LOCK_SURFACE_MISMATCH:expected=${expectedScriptPackages.join(",")}:actual=${actualScriptPackages.join(",")}`,
  );
}

console.log("LOCK_INSTALL_SCRIPT_SURFACE=PASS");
console.log(`LOCK_INSTALL_SCRIPT_PACKAGE_COUNT=${actualScriptPackages.length}`);

run("npm", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"]);

const rebuildSpecs = [];
for (const [name, version] of approvedInstallScripts) {
  const packageJsonPath = path.join("node_modules", ...name.split("/"), "package.json");
  if (!fs.existsSync(packageJsonPath)) {
    if (optionalOnThisPlatform.has(name)) continue;
    throw new Error(`APPROVED_INSTALL_SCRIPT_PACKAGE_MISSING:${name}@${version}`);
  }
  const installed = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
  if (installed.version !== version) {
    throw new Error(`APPROVED_INSTALL_SCRIPT_VERSION_MISMATCH:${name}:${installed.version}:${version}`);
  }
  rebuildSpecs.push(`${name}@${version}`);
}

if (rebuildSpecs.length === 0) {
  throw new Error("NO_APPROVED_INSTALL_SCRIPT_PACKAGES_PRESENT");
}

run("npm", ["rebuild", ...rebuildSpecs, "--no-audit", "--no-fund"]);

console.log(`APPROVED_INSTALL_SCRIPT_REBUILD_COUNT=${rebuildSpecs.length}`);
console.log("LOCKED_DEPENDENCY_INSTALL=PASS");
