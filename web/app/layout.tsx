import type { Metadata } from "next";
import { PublicSiteNav } from "../components/public-site-nav";
import "./globals.css";
import "./public-shell.css";

const PUBLIC_DESCRIPTION = "Publicly inspectable quantitative research system with sanitized product views and an authenticated founder workspace.";

export const metadata: Metadata = {
  title: {
    default: "DeltaGrid Research Engine",
    template: "%s · DeltaGrid",
  },
  description: PUBLIC_DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: "DeltaGrid",
    title: "DeltaGrid Research Engine",
    description: PUBLIC_DESCRIPTION,
  },
  twitter: {
    card: "summary",
    title: "DeltaGrid Research Engine",
    description: PUBLIC_DESCRIPTION,
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">Skip to content</a>
        <header className="site-header">
          <PublicSiteNav />
        </header>
        <div id="main-content" tabIndex={-1}>{children}</div>
        <footer className="site-footer">
          <p>Public Demo Mode uses sanitized deterministic fixtures. Live founder data, authenticated APIs and write controls require Founder Mode. Website state never creates DeltaGrid authority.</p>
        </footer>
      </body>
    </html>
  );
}
