# Live monitoring

DeltaGrid's live monitor has two jobs: prove that the public observer remains reachable and sanitized, and prove that anonymous requests still cannot cross into Founder Gateway surfaces.

The workflow runs on pull requests, pushes to `main`, an hourly schedule, and manual dispatch. Those trigger classes use separate concurrency groups. A new push may replace an older push check, and a newer scheduled run may replace an older scheduled run, but a source-code push must not cancel an hourly production-parity check that is already measuring the deployed system.

Scheduled and manual runs additionally compare the public `deltagrid-release.json` marker with current `main`. That parity check is intentionally separate from pull-request and push checks because public releases are manual; a brief source-versus-production gap after merge is expected. A scheduled parity failure means the deployed observer is stale or its release marker cannot be trusted and should be treated as an operational incident until explained.

The monitor remains read-only. It does not use deployment credentials, Founder Gateway credentials, private research state, or any research/trading authority.
