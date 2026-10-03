import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

function fail(code, detail = "") {
  throw new Error(detail ? `${code}:${detail}` : code);
}

function vulnerabilityTotal(audit) {
  const total = audit?.metadata?.vulnerabilities?.total;
  if (!Number.isInteger(total) || total < 0) fail("AUDIT_METADATA_INVALID");
  return total;
}

function advisoryId(advisory) {
  const match = String(advisory?.url ?? "").match(/\/advisories\/(GHSA-[a-z0-9-]+)$/u);
  if (!match) fail("AUDIT_ADVISORY_ID_INVALID", String(advisory?.url ?? "missing"));
  return match[1];
}

function collectAdvisories(name, vulnerabilities, visiting = new Set()) {
  if (visiting.has(name)) fail("AUDIT_VULNERABILITY_CYCLE", name);
  const vulnerability = vulnerabilities[name];
  if (!vulnerability || !Array.isArray(vulnerability.via)) {
    fail("AUDIT_VULNERABILITY_INVALID", name);
  }
  const next = new Set(visiting);
  next.add(name);
  const advisories = [];
  for (const via of vulnerability.via) {
    if (typeof via === "string") {
      advisories.push(...collectAdvisories(via, vulnerabilities, next));
    } else if (via && typeof via === "object") {
      advisories.push(via);
    } else {
      fail("AUDIT_VIA_INVALID", name);
    }
  }
  if (advisories.length === 0) fail("AUDIT_ADVISORY_MISSING", name);
  return advisories;
}

export function evaluateAudit({ fullAudit, runtimeAudit, lock, policy, today }) {
  if (!/^\d{4}-\d{2}-\d{2}$/u.test(today)) fail("AUDIT_DATE_INVALID", today);

  const runtimeVulnerabilities = runtimeAudit?.vulnerabilities ?? {};
  if (vulnerabilityTotal(runtimeAudit) !== 0 || Object.keys(runtimeVulnerabilities).length !== 0) {
    fail("RUNTIME_DEPENDENCY_AUDIT_FAILED");
  }

  const exceptions = policy?.auditExceptions ?? [];
  const exceptionByAdvisory = new Map();
  for (const exception of exceptions) {
    if (
      !/^GHSA-[a-z0-9-]+$/u.test(exception?.advisory ?? "") ||
      typeof exception?.package !== "string" ||
      typeof exception?.version !== "string" ||
      exception?.reach !== "dev-only" ||
      !/^\d{4}-\d{2}-\d{2}$/u.test(exception?.expiresOn ?? "")
    ) {
      fail("AUDIT_EXCEPTION_INVALID");
    }
    if (exceptionByAdvisory.has(exception.advisory)) {
      fail("AUDIT_EXCEPTION_DUPLICATE", exception.advisory);
    }
    if (today > exception.expiresOn) {
      fail("AUDIT_EXCEPTION_EXPIRED", `${exception.advisory}:${exception.expiresOn}`);
    }
    exceptionByAdvisory.set(exception.advisory, exception);
  }

  const vulnerabilities = fullAudit?.vulnerabilities ?? {};
  if (vulnerabilityTotal(fullAudit) !== Object.keys(vulnerabilities).length) {
    fail("AUDIT_VULNERABILITY_COUNT_MISMATCH");
  }

  const usedExceptions = new Set();
  for (const [name, vulnerability] of Object.entries(vulnerabilities)) {
    if (!Array.isArray(vulnerability.nodes) || vulnerability.nodes.length === 0) {
      fail("AUDIT_VULNERABILITY_NODES_INVALID", name);
    }
    for (const node of vulnerability.nodes) {
      const metadata = lock?.packages?.[node];
      if (!metadata) fail("AUDIT_LOCK_NODE_MISSING", node);
      if (metadata.dev !== true) fail("AUDIT_NON_DEV_REACH", node);
    }

    for (const advisory of collectAdvisories(name, vulnerabilities)) {
      const id = advisoryId(advisory);
      const exception = exceptionByAdvisory.get(id);
      if (!exception) fail("AUDIT_ADVISORY_UNEXPECTED", id);
      if (advisory.name !== exception.package || advisory.dependency !== exception.package) {
        fail("AUDIT_ADVISORY_PACKAGE_MISMATCH", id);
      }
      const packageNode = `node_modules/${exception.package}`;
      const packageMetadata = lock?.packages?.[packageNode];
      if (!packageMetadata) fail("AUDIT_EXCEPTION_PACKAGE_MISSING", packageNode);
      if (packageMetadata.version !== exception.version) {
        fail(
          "AUDIT_EXCEPTION_VERSION_MISMATCH",
          `${exception.package}:${packageMetadata.version}:${exception.version}`,
        );
      }
      if (packageMetadata.dev !== true) fail("AUDIT_NON_DEV_REACH", packageNode);
      usedExceptions.add(id);
    }
  }

  for (const id of exceptionByAdvisory.keys()) {
    if (!usedExceptions.has(id)) fail("AUDIT_EXCEPTION_UNUSED", id);
  }

  return exceptions.map(({ advisory, package: packageName, version, expiresOn }) => ({
    advisory,
    package: packageName,
    version,
    expiresOn,
  }));
}

function runAudit(args) {
  const result = spawnSync("npm", ["audit", "--json", ...args], {
    encoding: "utf8",
    env: process.env,
  });
  if (result.error) throw result.error;
  if (!result.stdout) fail("NPM_AUDIT_OUTPUT_MISSING", args.join(","));
  try {
    return JSON.parse(result.stdout);
  } catch {
    fail("NPM_AUDIT_OUTPUT_INVALID", args.join(","));
  }
}

function main() {
  const fullAudit = runAudit([]);
  const runtimeAudit = runAudit(["--omit=dev"]);
  const lock = JSON.parse(fs.readFileSync("package-lock.json", "utf8"));
  const policy = JSON.parse(
    fs.readFileSync(new URL("./dependency-policy.json", import.meta.url), "utf8"),
  );
  const today = new Date().toISOString().slice(0, 10);
  const exceptions = evaluateAudit({ fullAudit, runtimeAudit, lock, policy, today });

  console.log("RUNTIME_DEPENDENCY_AUDIT=PASS");
  for (const exception of exceptions) {
    console.log(
      `AUDIT_EXCEPTION=${exception.advisory}:${exception.package}@${exception.version}:DEV_ONLY:EXPIRES=${exception.expiresOn}`,
    );
  }
  console.log("DEPENDENCY_AUDIT=PASS");
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}
