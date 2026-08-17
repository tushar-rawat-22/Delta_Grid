import { useState } from "react";
import type { PreregistrationReview } from "./preregistration-model.ts";
import {
  compilePreregistrationHandoffManifest,
  type PreregistrationHandoffManifest,
} from "./preregistration-handoff-model.ts";

export function PreregistrationHandoffAction({
  review,
}: {
  review: PreregistrationReview;
}) {
  const [manifest, setManifest] = useState<PreregistrationHandoffManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      setManifest(await compilePreregistrationHandoffManifest(review));
    } catch (cause) {
      setManifest(null);
      setError(cause instanceof Error ? cause.message : "PREREGISTRATION_HANDOFF_FAILED");
    } finally {
      setBusy(false);
    }
  }

  const downloadHref = manifest
    ? `data:application/json;charset=utf-8,${encodeURIComponent(`${manifest.canonical_handoff_json}\n`)}`
    : "";

  return (
    <section className="prereg-section">
      <header>
        <span>Trusted-local handoff</span>
        <b>{manifest ? "MANIFEST READY" : "NO AUTHORITY"}</b>
      </header>
      <div className="prereg-body">
        <p className="prereg-final-boundary">
          This manifest is a deterministic transfer artifact only. It tells the trusted local
          operator which canonical Mission 94/101/102/103 owners must resolve the remaining
          bindings. It cannot issue a permit, reserve a trial, claim an execution specification,
          open protected evidence, or authorize research execution.
        </p>

        <button
          type="button"
          className="primary-button"
          onClick={() => void generate()}
          disabled={busy || !review.structural_lock_ready}
        >
          {busy ? "Generating…" : "Generate handoff manifest"}
        </button>

        {error ? <div className="prereg-error">{error.replaceAll("_", " ").toLowerCase()}</div> : null}

        {manifest ? (
          <>
            <div className="prereg-identity">
              <span>Handoff identity</span>
              <strong>{manifest.handoff_id}</strong>
              <code>{manifest.canonical_handoff_hash_sha256}</code>
            </div>
            <div className="prereg-bindings">
              {manifest.canonical_resolution_requirements.map((requirement) => (
                <div key={requirement.binding}>
                  <span>{requirement.binding.replaceAll("_", " ")}</span>
                  <strong>{requirement.owner}</strong>
                  <small>UNRESOLVED · LOCAL OPERATOR ONLY · BROWSER WRITABLE FALSE</small>
                </div>
              ))}
            </div>
            <a
              className="secondary-button"
              href={downloadHref}
              download={`${manifest.handoff_id}.json`}
            >
              Download canonical handoff JSON
            </a>
          </>
        ) : null}
      </div>
    </section>
  );
}
