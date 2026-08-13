import Link from "next/link";

export default function NotFound() {
  return (
    <main>
      <section className="hero compact-hero">
        <p className="eyebrow">404 · Not found</p>
        <h1>This observer has no route for that request.</h1>
        <p className="lede">No fallback data or inferred state is substituted for a missing public surface.</p>
        <Link className="button-link" href="/">Return to overview</Link>
      </section>
    </main>
  );
}
