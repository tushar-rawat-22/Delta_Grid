import assert from "node:assert/strict";
import test from "node:test";

import { evaluateAudit } from "../scripts/audit-dependencies.mjs";

const advisory = {
  name: "braces",
  dependency: "braces",
  url: "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm",
  severity: "high",
};

function fixture() {
  return {
    fullAudit: {
      metadata: { vulnerabilities: { total: 1 } },
      vulnerabilities: {
        braces: {
          severity: "high",
          via: [structuredClone(advisory)],
          nodes: ["node_modules/braces"],
        },
      },
    },
    runtimeAudit: {
      metadata: { vulnerabilities: { total: 0 } },
      vulnerabilities: {},
    },
    lock: {
      packages: {
        "node_modules/braces": { version: "3.0.3", dev: true },
      },
    },
    policy: {
      auditExceptions: [
        {
          advisory: "GHSA-vfj7-8cjw-p6xm",
          package: "braces",
          version: "3.0.3",
          reach: "dev-only",
          expiresOn: "2026-11-03",
        },
      ],
    },
    today: "2026-10-04",
  };
}

test("permits only the exact time-bounded dev-only advisory", () => {
  const result = evaluateAudit(fixture());
  assert.deepEqual(result, [
    {
      advisory: "GHSA-vfj7-8cjw-p6xm",
      package: "braces",
      version: "3.0.3",
      expiresOn: "2026-11-03",
    },
  ]);
});

test("fails closed on an unexpected advisory", () => {
  const input = fixture();
  input.fullAudit.vulnerabilities.braces.via[0].url =
    "https://github.com/advisories/GHSA-xxxx-yyyy-zzzz";
  assert.throws(() => evaluateAudit(input), /AUDIT_ADVISORY_UNEXPECTED/u);
});

test("fails closed when the affected package reaches runtime", () => {
  const input = fixture();
  input.lock.packages["node_modules/braces"].dev = false;
  assert.throws(() => evaluateAudit(input), /AUDIT_NON_DEV_REACH/u);
});

test("fails closed on any runtime advisory", () => {
  const input = fixture();
  input.runtimeAudit.metadata.vulnerabilities.total = 1;
  (input.runtimeAudit.vulnerabilities as Record<string, unknown>).braces = structuredClone(
    input.fullAudit.vulnerabilities.braces,
  );
  assert.throws(() => evaluateAudit(input), /RUNTIME_DEPENDENCY_AUDIT_FAILED/u);
});

test("fails closed after the exception expires", () => {
  const input = fixture();
  input.today = "2026-11-04";
  assert.throws(() => evaluateAudit(input), /AUDIT_EXCEPTION_EXPIRED/u);
});

test("fails closed when the exception no longer matches the installed version", () => {
  const input = fixture();
  input.lock.packages["node_modules/braces"].version = "3.0.4";
  assert.throws(() => evaluateAudit(input), /AUDIT_EXCEPTION_VERSION_MISMATCH/u);
});
