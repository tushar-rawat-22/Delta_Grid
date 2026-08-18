import { useMemo, useState } from "react";
import { PreregistrationHandoffAction } from "./preregistration-handoff-action.tsx";
import {
  compilePreregistrationReview,
  PREREGISTRATION_HEADINGS,
  type PreregistrationReview,
} from "./preregistration-model.ts";

type ThesisRecord = {
  record_id: string;
  record_type: string;
  title: string;
  body: string;
  status: string;
  revision: number;
  updated_at: string;
};

type BootstrapSlice = {
  records: ThesisRecord[];
  boundary: "NON_RAB1_RESEARCH_ONLY";
  authority_effect: "NONE";
};

type LoadState = "IDLE" | "LOADING" | "READY" | "FAILED";

export function PreregistrationWorkbench() {
  const [open, setOpen] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>("IDLE");
  const [theses, setTheses] = useState<ThesisRecord[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [review, setReview] = useState<PreregistrationReview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);

  const selected = useMemo(
    () => theses.find((record) => record.record_id === selectedId) ?? null,
    [selectedId, theses],
  );

  async function openWorkbench() {
    setOpen(true);
    if (loadState === "READY" || loadState === "LOADING") return;

    setLoadState("LOADING");
    setError(null);
    try {
      const response = await fetch("/api/research/v1/bootstrap", {
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
      if (!response.ok) throw new Error(`BOOTSTRAP_REQUEST_FAILED_${response.status}`);
      const payload = await response.json() as BootstrapSlice;
      if (payload.boundary !== "NON_RAB1_RESEARCH_ONLY" || payload.authority_effect !== "NONE") {
        throw new Error("PREREGISTRATION_BOOTSTRAP_BOUNDARY_INVALID");
      }
      const next = payload.records.filter(
        (record) => record.record_type === "THESIS" && Boolean(record.record_id),
      );
      setTheses(next);
      setSelectedId((current) => current || next[0]?.record_id || "");
      setLoadState("READY");
    } catch (cause) {
      setLoadState("FAILED");
      setError(cause instanceof Error ? cause.message : "PREREGISTRATION_BOOTSTRAP_FAILED");
    }
  }

  async function compileSelected() {
    if (!selected) return;
    setCompiling(true);
    setError(null);
    setReview(null);
    try {
      const next = await compilePreregistrationReview({
        record_id: selected.record_id,
        revision: selected.revision,
        title: selected.title,
        body: selected.body,
      });
      setReview(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "PREREGISTRATION_COMPILE_FAILED");
    } finally {
      setCompiling(false);
    }
  }

  function closeWorkbench() {
    setOpen(false);
  }

  return (
    <>
      <button
        type="button"
        className="prereg-launcher"
        onClick={() => void openWorkbench()}
        aria-haspopup="dialog"
      >
        <span>Pre-admission</span>
        <strong>Preregistration review</strong>
      </button>

      {open ? (
        <div className="prereg-layer">
          <button
            type="button"
            className="prereg-backdrop"
            onClick={closeWorkbench}
            aria-label="Close preregistration review"
          />
          <aside
            className="prereg-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="prereg-title"
          >
            <header className="prereg-head">
              <div>
                <p>Founder scientific control</p>
                <h2 id="prereg-title">Preregistration review</h2>
              </div>
              <button type="button" onClick={closeWorkbench} aria-label="Close preregistration review">×</button>
            </header>

            <div className="prereg-boundary">
              <strong>NON_RAB1 · AUTHORITY NONE</strong>
              <span>Review only · no persistence · no trial reservation · no execution authorization</span>
            </div>

            {loadState === "LOADING" ? <p className="prereg-message">Loading saved THESIS records…</p> : null}
            {error ? <div className="prereg-error">{humanizeError(error)}</div> : null}

            {loadState === "READY" ? (
              <div className="prereg-body">
                <label className="prereg-select">
                  Saved thesis
                  <select
                    value={selectedId}
                    onChange={(event) => {
                      setSelectedId(event.target.value);
                      setReview(null);
                      setError(null);
                    }}
                  >
                    {theses.length ? null : <option value="">No saved THESIS records</option>}
                    {theses.map((record) => (
                      <option key={record.record_id} value={record.record_id}>
                        {record.title} · rev {record.revision}
                      </option>
                    ))}
                  </select>
                </label>

                {selected ? (
                  <section className="prereg-source">
                    <div>
                      <span>{selected.status}</span>
                      <strong>{selected.title}</strong>
                      <small>Revision {selected.revision} · {selected.record_id}</small>
                    </div>
                    <button
                      type="button"
                      onClick={() => void compileSelected()}
                      disabled={compiling}
                    >
                      {compiling ? "Compiling…" : "Compile review"}
                    </button>
                  </section>
                ) : (
                  <p className="prereg-message">
                    No saved THESIS exists yet. Close this panel, open Hypotheses, choose a Candidate question and click Draft thesis, then complete and Save record. You can also use Notebook → New record → Type THESIS.
                  </p>
                )}

                {review ? <ReviewResult review={review} /> : null}
              </div>
            ) : null}
          </aside>
        </div>
      ) : null}
    </>
  );
}

function ReviewResult({ review }: { review: PreregistrationReview }) {
  const bindings = Object.entries(review.canonical_bindings);
  return (
    <div className="prereg-result">
      <section className={review.structural_lock_ready ? "prereg-verdict ready" : "prereg-verdict blocked"}>
        <span>Structural review</span>
        <strong>{review.structural_lock_ready ? "READY FOR CANONICAL BINDING" : "BLOCKED"}</strong>
        <p>
          {review.structural_lock_ready
            ? "All founder scientific sections are complete. Canonical dataset, permit, trial, execution-family and statistical-program bindings remain unresolved outside the browser."
            : `${review.blocking_reasons.length} blocking condition${review.blocking_reasons.length === 1 ? "" : "s"} remain.`}
        </p>
      </section>

      <section className="prereg-section">
        <header><span>Scientific protocol</span><b>{PREREGISTRATION_HEADINGS.length}/10 sections</b></header>
        <div className="prereg-checklist">
          {PREREGISTRATION_HEADINGS.map((heading) => {
            const blocked = review.blocking_reasons.some((reason) => reason.endsWith(heading));
            return (
              <div key={heading}>
                <span className={blocked ? "blocked" : "ready"}>{blocked ? "!" : "✓"}</span>
                <strong>{heading}</strong>
                <small>{blocked ? "Needs founder completion" : "Present"}</small>
              </div>
            );
          })}
        </div>
      </section>

      {review.blocking_reasons.length ? (
        <section className="prereg-section">
          <header><span>Blocking reasons</span><b>{review.blocking_reasons.length}</b></header>
          <ul className="prereg-blockers">
            {review.blocking_reasons.map((reason) => <li key={reason}>{reason.replaceAll("_", " ")}</li>)}
          </ul>
        </section>
      ) : null}

      <section className="prereg-section">
        <header><span>Canonical bindings</span><b>UNRESOLVED</b></header>
        <div className="prereg-bindings">
          {bindings.map(([name, binding]) => (
            <div key={name}>
              <span>{name.replaceAll("_", " ")}</span>
              <strong>{binding.owner}</strong>
              <small>{binding.status} · browser writable {String(binding.browser_writable).toUpperCase()}</small>
            </div>
          ))}
        </div>
      </section>

      <section className="prereg-identity">
        <span>Deterministic review identity</span>
        <strong>{review.review_id}</strong>
        <code>{review.canonical_review_hash_sha256}</code>
      </section>

      {review.structural_lock_ready ? <PreregistrationHandoffAction review={review} /> : null}

      <p className="prereg-final-boundary">
        This review creates no authority. It does not persist a lock, reserve a trial, consume a permit,
        open protected evidence, authorize Mission 104, authorize execution, create a trading signal,
        place an order, or allocate capital.
      </p>
    </div>
  );
}

function humanizeError(value: string): string {
  const known: Record<string, string> = {
    PREREGISTRATION_SECTION_MISSING: "The selected thesis does not contain all ten preregistration sections.",
    PREREGISTRATION_SECTION_ORDER_INVALID: "The preregistration sections are not in canonical order.",
    PREREGISTRATION_THESIS_IDENTITY_INVALID: "The selected thesis does not have a valid saved identity and revision.",
  };
  return known[value] ?? value.replaceAll("_", " ").toLowerCase();
}
