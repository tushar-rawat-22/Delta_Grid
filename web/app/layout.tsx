import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "DeltaGrid Research Engine",
    template: "%s · DeltaGrid",
  },
  description: "Founder-only market research workspace with a read-only public product overview.",
  robots: { index: false, follow: false },
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
            </div>
          </nav>
        </header>
        <div id="main-content">{children}</div>
        <footer className="site-footer">
          <p>Public product overview and read-only observer. Website state never creates DeltaGrid authority.</p>
        </footer>
      </body>
    </html>
  );
}
