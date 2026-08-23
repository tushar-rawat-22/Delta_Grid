# Quick review

Live observer: https://deltagrid-observer.tushar142004.workers.dev

DeltaGrid has a public observer because the project is easier to review when the research state and controls are visible. It is not the Founder workspace and it is not a trading console.

If you only have a few minutes, open the observer first. The front page shows the current research status, configured coverage, provider limits, authority state, and sanitized workspace screenshots. The `/research` route is a deterministic demo; it does not load private Founder records.

For the implementation, [ARCHITECTURE.md](ARCHITECTURE.md) describes the split between the public Worker and the authenticated Founder Gateway. [SECURITY_BOUNDARY.md](SECURITY_BOUNDARY.md) covers the checks that keep private routes and data out of the public build. [CONTINUITY.md](CONTINUITY.md) is the current operations handoff when release or monitoring details matter.

A few things are intentionally boring. The public site is static. Anonymous requests to Founder surfaces are denied or redirected through Cloudflare Access. Releases are tied to a reviewed `main` commit, and monitoring checks whether production has fallen behind source.

None of that is evidence of a profitable strategy. DeltaGrid currently has no validated alpha, no selected candidate, and no paper/live trading or capital authority. Those limits are part of the system, not disclaimers added for the website.
