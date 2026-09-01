export type PublicReleaseProvenance =
  | {
      status: "VERIFIED LIVE";
      releaseSha: string;
      detail: string;
    }
  | {
      status: "UNVERIFIED";
      releaseSha: null;
      detail: string;
    };

const RELEASE_SHA_PATTERN = /^[0-9a-f]{40}$/;

export function derivePublicReleaseProvenance(value: unknown): PublicReleaseProvenance {
  if (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.keys(value).length === 1 &&
    "release_sha" in value &&
    typeof value.release_sha === "string" &&
    RELEASE_SHA_PATTERN.test(value.release_sha)
  ) {
    return {
      status: "VERIFIED LIVE",
      releaseSha: value.release_sha,
      detail: `The public release marker reports deployed revision ${value.release_sha.slice(0, 12)}. This proves live observer identity only; it does not grant research, trading or capital authority.`,
    };
  }

  return {
    status: "UNVERIFIED",
    releaseSha: null,
    detail: "The public release marker is missing or invalid, so this page fails closed rather than claiming a production-current revision.",
  };
}
