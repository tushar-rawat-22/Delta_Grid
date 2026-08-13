# DeltaGrid Research Engine

The Research Engine is a founder-only market-research workspace served by the existing `deltagrid-founder-gateway` Worker. It does not create a new hostname, Access application, audience or hosting authority.

## Product surface

- `/research` serves the React workspace after founder JWT validation.
- `/api/research/v1/bootstrap` returns the founder-scoped workspace and a short-lived CSRF proof.
- Markets, dossiers, comparisons, macro, notebook, provider health and founder exports use versioned same-origin routes.
- Public screenshots are 1440×900 captures of the real interface in development-only sanitized fixture mode.

## Provider policy

| Provider | Data | Credential | Collection policy |
| --- | --- | --- | --- |
| Coinbase Exchange | Settled hourly BTC, ETH and SOL candles | None | One due instrument per scheduled cycle |
| Alpha Vantage | Recent raw daily US equities and ETFs | Worker secret | Free compact endpoint only; quota responses remain explicit |
| FRED | Fixed macro series | Worker secret | Fixed series registry with attribution-required rights state |
| SEC Company Facts | Fixed CIK fundamentals | None | Identified DeltaGrid user agent and bounded facts subset |
| Treasury Fiscal Data | Latest Debt to the Penny | None | Fixed official dataset endpoint |

The five-minute UTC cron advances at most one due instrument per provider. A failed or quota-limited source therefore cannot block independent sources. Duplicate scheduled delivery cannot duplicate collection for the same provider, instrument and time bucket. Responses are capped at 4 MiB, except the fixed SEC Company Facts endpoint which has an isolated 8 MiB ceiling for legitimate large-issuer payloads. Every response is hashed, parsed through provider-specific schemas and recorded in append-only receipts. Raw provider payloads are not stored in D1. Network, rate-limit, and upstream 5xx failures retry after five minutes; structural failures retain the one-hour backoff and provider quota exhaustion retains the full-day backoff.

## Data semantics

- Alpha Vantage daily observations are labeled raw/unadjusted.
- Coinbase excludes the current unfinished hourly candle.
- Metrics disclose their window and return null when history or variance is insufficient.
- Comparisons use common observation timestamps only.
- FRED and Treasury cards show observation date, units and frequency rather than implying live freshness.
- SEC facts retain filing date, period end, form and accession number.

## Deployment and rollback

1. Run `npm run check` from a clean merged commit.
2. Export the remote D1 database before applying migration `0003_research_engine.sql`.
3. Configure `DELTAGRID_RESEARCH_CSRF_KEY`, `ALPHA_VANTAGE_API_KEY` and `FRED_API_KEY` as Worker secrets.
4. Apply D1 migrations, deploy the founder Worker, and verify Access denial plus founder success.
5. Deploy the public static Worker only after founder acceptance.
6. Roll back code with the prior Cloudflare Worker version. The additive migration is retained; old code does not reference the new tables.

## Non-authority statement

All research-engine schema objects carry `NON_RAB1_RESEARCH_ONLY` and authority effect `NONE`. The engine has no brokerage, exchange credential, order, paper-trading, allocation, capital or self-authorization interface. Mission 104 remains not authorized.
