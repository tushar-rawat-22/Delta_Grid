import fs from "node:fs";
import path from "node:path";
import { verifyProjectionPackage } from "./projection/verify.ts";

export const P1_CORE_COMMIT = "d94441f2f32fd8edc7b416beecd88b2b087d01a9";
export const P1_PROJECTION_SHA256 = "0e13dae7cddddff1110d79630682bfbc1495f1bc23d5ea95cf15e2906fb967c4";
export const P1_PROJECTION_DIRECTORY = "data/public-projection/v1/current";

function readSnapshotFile(name: "projection.json" | "manifest.json"): string {
  return fs.readFileSync(path.join(process.cwd(), P1_PROJECTION_DIRECTORY, name), "utf8");
}

const verified = verifyProjectionPackage(
  readSnapshotFile("projection.json"),
  readSnapshotFile("manifest.json"),
  P1_CORE_COMMIT,
);

if (verified.projectionSha256 !== P1_PROJECTION_SHA256) {
  throw new Error(`P1_3_PROJECTION_SHA_MISMATCH:${verified.projectionSha256}`);
}

export const currentProjection = verified;
export const projectionAuthority = currentProjection.projection.authority;
export const verifiedProjectionSource =
  `P1.1 verified projection · core ${P1_CORE_COMMIT.slice(0, 12)} · sha256 ${P1_PROJECTION_SHA256.slice(0, 12)}`;

export function requireClosedAuthority(field: keyof typeof projectionAuthority): "NOT AUTHORIZED" {
  if (projectionAuthority[field] !== false) {
    throw new Error(`P1_3_AUTHORITY_NOT_CLOSED:${field}`);
  }
  return "NOT AUTHORIZED";
}

export function requireNoCapitalAuthority(): "NONE" {
  requireClosedAuthority("capital_deployment");
  return "NONE";
}
