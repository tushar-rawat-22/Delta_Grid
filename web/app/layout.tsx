import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

const FOUNDER_RESEARCH_URL = "https://deltagrid-founder-gateway.tushar142004.workers.dev/research";

export const metadata: Metadata = {
  title: {
    default: "DeltaGrid Research Engine",
    template: "%s · DeltaGrid",
  },
  description: "Publicly inspectable quantitative research system with sanitized product views and an authenticated founder workspace.",
  robots: { index: true, follow: true },
};

const routes = [
  ["/", "Overview"],
  ["/markets", "Markets"],
  ["/research", "Research"],
  ["/evidence", "Evidence"],
  ["/missions", "Missions"],
  ["/system", "System"],
  ["/risk", "Risk"],
  ["/docs", "Docs"],
  ["/about", "About"],
] as const;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <header className="site-header">
          <nav className="nav-shell" aria-label="Primary">
            <Link className="brand" href="/" aria-label="DeltaGrid Research Engine home">
              <span className="brand-mark" aria-hidden="true">Δ</span>
              <span>DeltaGrid</span>
              <small>Research</small>
            </Link>
            <div className="nav-links">
              {routes.slice(1).map(([href, label]) => <Link key={href} href={href}>{label}</Link>)}
              <a href={FOUNDER_RESEARCH_URL}>Log in</a>
            </div>
          </nav>
        </header>
        <div id="main-content">{children}</div>
        <footer className="site-footer">
          <p>Public product shell and sanitized observer. Live founder data and controls require authenticated founder access. Website state never creates DeltaGrid authority.</p>
        </footer>
      </body>
    </html>
  );
}
