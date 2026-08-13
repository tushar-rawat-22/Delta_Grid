import fs from "node:fs";
import path from "node:path";
import { verifyProjectionPackage } from "../lib/projection/verify.ts";

export const EXPECTED_CORE_COMMIT = "d94441f2f32fd8edc7b416beecd88b2b087d01a9";
export const EXPECTED_PROJECTION_SHA256 = "0e13dae7cddddff1110d79630682bfbc1495f1bc23d5ea95cf15e2906fb967c4";

const directory = process.argv[2] ?? "data/public-projection/v1/current";
const projectionRaw = fs.readFileSync(path.join(directory, "projection.json"), "utf8");
const manifestRaw = fs.readFileSync(path.join(directory, "manifest.json"), "utf8");
const verified = verifyProjectionPackage(projectionRaw, manifestRaw, EXPECTED_CORE_COMMIT);

if (verified.projectionSha256 !== EXPECTED_PROJECTION_SHA256) {
  throw new Error(`UNEXPECTED_PROJECTION_SHA256:${verified.projectionSha256}`);
}

console.log(`P1_3_PROJECTION_DIRECTORY=${directory}`);
console.log(`P1_3_CORE_COMMIT=${verified.manifest.repository_commit}`);
console.log(`P1_3_PROJECTION_SHA256=${verified.projectionSha256}`);
console.log("P1_3_PROJECTION_SNAPSHOT_VERIFY=PASS");
