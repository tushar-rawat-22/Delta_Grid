import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

type PackageFixture = {
  dependencies: Record<string, string>;
  devDependencies: Record<string, string>;
  allowScripts: Record<string, boolean>;
  [key: string]: unknown;
};

type LockEntry = {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  version?: string;
  hasInstallScript?: boolean;
};

type LockFixture = {
  lockfileVersion: number;
  packages: Record<string, LockEntry>;
};

const verifyScript = path.resolve("scripts/verify-dependencies.mjs");
const baselinePackage = JSON.parse(fs.readFileSync("package.json", "utf8")) as PackageFixture;

function lockFor(pkg: PackageFixture): LockFixture {
  const packages: Record<string, LockEntry> = {
    "": {
      dependencies: { ...pkg.dependencies },
      devDependencies: { ...pkg.devDependencies },
    },
  };
  for (const spec of Object.keys(pkg.allowScripts)) {
    const separator = spec.lastIndexOf("@");
    const name = spec.slice(0, separator);
    const version = spec.slice(separator + 1);
    packages[`node_modules/${name}`] = { version, hasInstallScript: true };
  }
  return { lockfileVersion: 3, packages };
}

function rootEntry(lock: LockFixture): LockEntry {
  const root = lock.packages[""];
  assert.ok(root);
  return root;
}

function runVerifier(
  mutate: (pkg: PackageFixture, lock: LockFixture) => void = () => {},
) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "deltagrid-dependency-policy-"));
  try {
    const pkg = structuredClone(baselinePackage);
    const lock = lockFor(pkg);
    mutate(pkg, lock);
    fs.writeFileSync(path.join(directory, "package.json"), `${JSON.stringify(pkg, null, 2)}\n`);
    fs.writeFileSync(path.join(directory, "package-lock.json"), `${JSON.stringify(lock, null, 2)}\n`);
    return spawnSync(process.execPath, [verifyScript], {
      cwd: directory,
      encoding: "utf8",
    });
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

test("a reviewed direct version bump does not require a second hard-coded version edit", () => {
  const result = runVerifier((pkg, lock) => {
    pkg.dependencies.jose = "999.0.1";
    const root = rootEntry(lock);
    assert.ok(root.dependencies);
    root.dependencies.jose = "999.0.1";
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /DEPENDENCY_POLICY=PASS/u);
});

test("a new direct dependency still fails closed", () => {
  const result = runVerifier((pkg, lock) => {
    pkg.dependencies["unreviewed-package"] = "1.0.0";
    const root = rootEntry(lock);
    assert.ok(root.dependencies);
    root.dependencies["unreviewed-package"] = "1.0.0";
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /DEPENDENCY_NAME_SET_MISMATCH:dependencies/u);
});

test("an unapproved install script still fails closed", () => {
  const result = runVerifier((_pkg, lock) => {
    lock.packages["node_modules/unreviewed-installer"] = {
      version: "1.0.0",
      hasInstallScript: true,
    };
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /INSTALL_SCRIPT_LOCK_SURFACE_MISMATCH/u);
});

test("non-exact direct dependency versions remain forbidden", () => {
  const result = runVerifier((pkg, lock) => {
    pkg.dependencies.jose = "^6.2.9";
    const root = rootEntry(lock);
    assert.ok(root.dependencies);
    root.dependencies.jose = "^6.2.9";
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /NON_EXACT_DIRECT_DEPENDENCY:jose/u);
});
