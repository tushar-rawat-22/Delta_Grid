"use client";

import { useEffect, useState } from "react";
import {
  derivePublicReleaseProvenance,
  type PublicReleaseProvenance,
} from "../lib/public-release-provenance";

const initialProvenance = derivePublicReleaseProvenance(null);

export function ReleaseProvenanceCard() {
  const [provenance, setProvenance] = useState<PublicReleaseProvenance>(initialProvenance);

  useEffect(() => {
    const controller = new AbortController();

    async function verifyLiveRelease() {
      try {
        const response = await fetch("/deltagrid-release.json", {
          cache: "no-store",
          headers: { Accept: "application/json" },
          signal: controller.signal,
        });
        if (!response.ok) {
          setProvenance(initialProvenance);
          return;
        }
        setProvenance(derivePublicReleaseProvenance(await response.json()));
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setProvenance(initialProvenance);
        }
      }
    }

    void verifyLiveRelease();
    return () => controller.abort();
  }, []);

  return (
    <article className="card" data-release-provenance={provenance.status}>
      <div className="card-topline">
        <h2>Release provenance</h2>
        <span className="badge">{provenance.status}</span>
      </div>
      <p>{provenance.detail}</p>
    </article>
  );
}
