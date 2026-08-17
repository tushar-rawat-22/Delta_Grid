"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const FOUNDER_RESEARCH_URL = "https://deltagrid-founder-gateway.tushar142004.workers.dev/research";

const routes = [
  ["/", "Overview"],
  ["/research", "Demo Mode"],
  ["/markets", "Markets"],
  ["/evidence", "Evidence"],
  ["/missions", "Missions"],
  ["/system", "System"],
  ["/risk", "Risk"],
  ["/docs", "Docs"],
  ["/about", "About"],
] as const;

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function PublicSiteNav() {
  const pathname = usePathname();

  return (
    <nav className="public-nav-shell" aria-label="DeltaGrid public product">
      <div className="public-nav-topline">
        <Link className="public-brand" href="/" aria-label="DeltaGrid Research Engine home">
          <span className="public-brand-mark" aria-hidden="true">Δ</span>
          <span className="public-brand-copy">
            <strong>DeltaGrid</strong>
            <small>Research Engine</small>
          </span>
        </Link>

        <div className="public-mode" aria-label="Current access mode">
          <span><i aria-hidden="true" />Public demo</span>
          <small>Sanitized fixtures · no writes</small>
        </div>

        <div className="public-nav-actions">
          <Link className="public-demo-button" href="/research">Open Demo</Link>
          <a className="public-login-button" href={FOUNDER_RESEARCH_URL}>Founder Log in <span aria-hidden="true">↗</span></a>
        </div>
      </div>

      <div className="public-route-row" aria-label="Public sections">
        {routes.map(([href, label]) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              className={active ? "public-route-link is-active" : "public-route-link"}
              aria-current={active ? "page" : undefined}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
