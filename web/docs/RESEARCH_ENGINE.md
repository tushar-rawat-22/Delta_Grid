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
| SEC XBRL Company Concept | Fixed CIK fundamentals | None | Five fixed concepts per company with an identified user agent |
| Treasury Fiscal Data | Latest Debt to the Penny | None | Fixed official dataset endpoint |

The five-minute UTC cron advances at most one due instrument per provider. A failed or quota-limited source therefore cannot block independent sources. Duplicate delivery cannot duplicate collection within the same five-minute provider-and-instrument bucket, while an incomplete claim can be retried in the next bucket. Responses are capped at 4 MiB. The SEC adapter requests exactly five allowlisted US-GAAP Company Concept documents sequentially; this avoids loading an issuer's multi-megabyte all-concepts document and remains far below SEC request guidance. The transport timeout covers both response headers and the bounded body read. Bounded response chunks are joined once before decoding. Every completed response is hashed, parsed through provider-specific schemas and recorded in append-only receipts. Batch-item failures identify only the fixed provider and a sanitized internal error code. Raw provider payloads are not stored in D1. Network, rate-limit, and retryable upstream 5xx failures retry after five minutes; TLS 525/526 failures return to the instrument's normal cadence, structural failures retain the one-hour backoff, and provider quota exhaustion retains the full-day backoff.

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

## Quant metric semantics

Research return horizons are elapsed-time horizons, not observation-count
shortcuts. A displayed 1D, 7D, or 30D return therefore requires an observation
at or before the corresponding UTC cutoff from the latest observation.

Realized volatility is annualized using the instrument cadence. Hourly crypto
uses 365 × 24 periods per year, daily crypto uses 365, daily U.S. equities and
ETFs use 252, and weekly series use 52.

These calculations remain inside `NON_RAB1_RESEARCH_ONLY`. They do not create
signals, recommendations, portfolio instructions, trading authority, or
RAB-1 evidence.

## Founder market intelligence brief

The private research workspace exposes an on-demand deterministic market
intelligence brief derived only from observations already stored by the
research engine.

The brief reports true elapsed 1D, 7D and 30D return coverage, one-day breadth
and observed movers, complete trailing seven-calendar-day volatility and
drawdown, selected cross-asset relationships using only exactly aligned
timestamps from up to 30 calendar days, latest series-specific macro changes,
and deterministic founder-attention flags.

Seven-day risk metrics fail closed until the complete calendar horizon exists.
Cross-asset relationships may use shorter available history, but publish the
actual overlap count and never interpolate missing timestamps. Macro series
with incompatible units are not ranked against one another.

The brief is loaded on demand rather than being added to the normal workspace
bootstrap. It introduces no provider request, database migration or write path.

It remains `NON_RAB1_RESEARCH_ONLY` with authority effect `NONE` and creates no
forecast, trade signal, recommendation, paper trade, order, position,
allocation or RAB-1 evidence.

## Founder hypothesis workbench

The private workspace includes a pre-admission hypothesis workbench that
connects deterministic Intelligence attention flags to founder-authored THESIS
records.

An Intelligence priority is an observation requiring attention; it is not
itself a hypothesis. Choosing `Draft thesis` creates only an unsaved browser
draft containing explicit sections for economic mechanism, falsification,
chronology, test plan, candidate and parameter budget, implementation costs,
multiple-testing family, decision rules, and review conditions.

Nothing is persisted until the founder explicitly saves the record through the
existing revisioned research-record API.

Saved hypotheses reuse the existing `research_records` and append-only
`research_record_revisions` mechanism. No new database or migration is
introduced.

Notebook statuses such as `DRAFT`, `ACTIVE`, and `WATCHING` are workflow labels
only. They do not reserve Mission 94 trials, consume Mission 101 permits,
invoke Mission 102 research execution, open Mission 103 protected evidence,
authorize Mission 104, or grant paper, live, exchange, order, allocation, or
capital authority.

The workbench remains `NON_RAB1_RESEARCH_ONLY` with authority effect `NONE`.
