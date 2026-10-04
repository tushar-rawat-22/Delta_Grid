import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const RELEASE_SHA_PATTERN = /^[0-9a-f]{40}$/;
const provenanceRoutes = ["markets", "evidence", "missions", "system", "risk", "docs", "about"];

export function bindPublicReleaseProvenance(root, releaseSha) {
  if (!RELEASE_SHA_PATTERN.test(releaseSha)) {
    throw new Error("PUBLIC_RELEASE_SHA_INVALID");
  }

  let verifiedRoutes = 0;
  for (const route of provenanceRoutes) {
    const file = findRoute(root, route);
    const html = fs.readFileSync(file, "utf8");
    if (
      html.includes('data-release-provenance="UNVERIFIED"') ||
      html.includes('data-release-provenance-status="UNVERIFIED"') ||
      html.includes('data-release-provenance-detail="UNVERIFIED"') ||
      !html.includes('data-release-provenance="VERIFIED LIVE"') ||
      !html.includes('data-release-provenance-status="VERIFIED LIVE">VERIFIED LIVE</span>') ||
      !html.includes(`data-release-sha="${releaseSha}"`) ||
      !html.includes(`Verified live release ${releaseSha.slice(0, 12)}.`)
    ) {
      throw new Error(`PUBLIC_RELEASE_BINDING_FAILED:/${route}`);
    }
    verifiedRoutes += 1;
  }

  for (const file of allFiles(root)) {
    if (!/\.(?:html|txt)$/u.test(file)) continue;
    const text = fs.readFileSync(file, "utf8");
    if (text.includes("data-release-provenance") && text.includes("UNVERIFIED")) {
      throw new Error(`PUBLIC_RELEASE_HYDRATION_PAYLOAD_UNVERIFIED:${file}`);
    }
  }

  fs.writeFileSync(
    path.join(root, "deltagrid-release.json"),
    `${JSON.stringify({ release_sha: releaseSha })}\n`,
  );

  if (verifiedRoutes !== provenanceRoutes.length) throw new Error("PUBLIC_RELEASE_ROUTE_COUNT_INVALID");
  return { verifiedRoutes, releaseSha };
}

function findRoute(root, route) {
  const candidates = [path.join(root, `${route}.html`), path.join(root, route, "index.html")];
  for (const candidate of candidates) if (fs.existsSync(candidate)) return candidate;
  throw new Error(`PUBLIC_RELEASE_ROUTE_MISSING:/${route}`);
}

function allFiles(current) {
  const output = [];
  for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
    const full = path.join(current, entry.name);
    if (entry.isDirectory()) output.push(...allFiles(full));
    else output.push(full);
  }
  return output;
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (invokedPath === fileURLToPath(import.meta.url)) {
  const releaseSha = process.argv[2] ?? "";
  const result = bindPublicReleaseProvenance("out", releaseSha);
  console.log(`PUBLIC_RELEASE_PROVENANCE_VERIFIED=${result.verifiedRoutes}`);
  console.log(`PUBLIC_RELEASE_SHA=${result.releaseSha}`);
}
