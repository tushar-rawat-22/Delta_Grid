import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const RELEASE_SHA_PATTERN = /^[0-9a-f]{40}$/;
const routes = ["", "markets", "research", "evidence", "missions", "system", "risk", "docs", "about"];
const unverifiedDetail =
  "This build has not been bound to a verified live release. Production deployment must prove the exact deployed revision before this status changes.";

export function bindPublicReleaseProvenance(root, releaseSha) {
  if (!RELEASE_SHA_PATTERN.test(releaseSha)) {
    throw new Error("PUBLIC_RELEASE_SHA_INVALID");
  }

  const verifiedDetail =
    `Verified live release ${releaseSha.slice(0, 12)}. The public release pipeline proved this exact deployed revision and rechecked the public/private boundary. This does not grant research, trading or capital authority.`;

  let boundRoutes = 0;
  for (const route of routes) {
    const file = findRoute(root, route);
    let html = fs.readFileSync(file, "utf8");

    const before = html;
    html = replaceExactlyOnce(
      html,
      'data-release-provenance="UNVERIFIED"',
      'data-release-provenance="VERIFIED LIVE"',
      `PUBLIC_RELEASE_CARD_BINDING_INVALID:/${route}`,
    );
    html = replaceExactlyOnce(
      html,
      'data-release-provenance-status="UNVERIFIED">UNVERIFIED</span>',
      'data-release-provenance-status="VERIFIED LIVE">VERIFIED LIVE</span>',
      `PUBLIC_RELEASE_STATUS_BINDING_INVALID:/${route}`,
    );
    html = replaceExactlyOnce(
      html,
      `data-release-provenance-detail="UNVERIFIED">${unverifiedDetail}</p>`,
      `data-release-provenance-detail="VERIFIED LIVE">${verifiedDetail}</p>`,
      `PUBLIC_RELEASE_DETAIL_BINDING_INVALID:/${route}`,
    );

    if (html === before || html.includes('data-release-provenance="UNVERIFIED"')) {
      throw new Error(`PUBLIC_RELEASE_BINDING_FAILED:/${route}`);
    }
    fs.writeFileSync(file, html);
    boundRoutes += 1;
  }

  fs.writeFileSync(
    path.join(root, "deltagrid-release.json"),
    `${JSON.stringify({ release_sha: releaseSha })}\n`,
  );

  if (boundRoutes !== routes.length) throw new Error("PUBLIC_RELEASE_ROUTE_COUNT_INVALID");
  return { boundRoutes, releaseSha };
}

function replaceExactlyOnce(text, from, to, code) {
  const first = text.indexOf(from);
  if (first < 0 || text.indexOf(from, first + from.length) >= 0) throw new Error(code);
  return `${text.slice(0, first)}${to}${text.slice(first + from.length)}`;
}

function findRoute(root, route) {
  const candidates = route === ""
    ? [path.join(root, "index.html")]
    : [path.join(root, `${route}.html`), path.join(root, route, "index.html")];
  for (const candidate of candidates) if (fs.existsSync(candidate)) return candidate;
  throw new Error(`PUBLIC_RELEASE_ROUTE_MISSING:/${route}`);
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (invokedPath === fileURLToPath(import.meta.url)) {
  const releaseSha = process.argv[2] ?? "";
  const result = bindPublicReleaseProvenance("out", releaseSha);
  console.log(`PUBLIC_RELEASE_PROVENANCE_BOUND=${result.boundRoutes}`);
  console.log(`PUBLIC_RELEASE_SHA=${result.releaseSha}`);
}
