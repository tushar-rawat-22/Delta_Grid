const RELEASE_SHA_PATTERN = /^[0-9a-f]{40}$/u;

const unverifiedDetail =
  "This build has not been bound to a verified live release. Production deployment must prove the exact deployed revision before this status changes.";

export type PublicReleaseProvenance = Readonly<{
  status: "UNVERIFIED" | "VERIFIED LIVE";
  detail: string;
  releaseSha: string | null;
}>;

export function publicReleaseProvenance(): PublicReleaseProvenance {
  const releaseSha = process.env.DELTAGRID_PUBLIC_RELEASE_SHA;
  if (releaseSha === undefined || releaseSha === "") {
    return { status: "UNVERIFIED", detail: unverifiedDetail, releaseSha: null };
  }
  if (!RELEASE_SHA_PATTERN.test(releaseSha)) {
    throw new Error("PUBLIC_RELEASE_SHA_INVALID");
  }
  return {
    status: "VERIFIED LIVE",
    detail:
      `Verified live release ${releaseSha.slice(0, 12)}. The public release pipeline proved this exact deployed revision and rechecked the public/private boundary. This does not grant research, trading or capital authority.`,
    releaseSha,
  };
}
