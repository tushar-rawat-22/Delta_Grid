# DeltaGrid Web Architecture

```text
Public core at exact admitted commit
        │ verified canonical projection
        ▼
Next.js static export ──► Cloudflare Static Assets ──► product landing + public observer

Founder browser ──► exact-founder Access + MFA ──► founder Worker
                         │                              ├──► authenticated /research assets
                         │                              ├──► /api/research/v1/*
                         │                              │          │
                         │                              │          ▼
                         │                              │    isolated research_* D1 tables
                         │                              ▼
                         │                        D1 command ledger
                         │                              ▲
Founder Mac agent ──► path-scoped Service Auth + HMAC ──┘
        │
        └── fixed local actions against exact clean core commit
```

The public and founder Workers remain separate deployments and exposure boundaries. The public deployment has no server state. The founder Worker serves research assets only after independently validating the Access JWT; API writes also require a short-lived, founder-bound CSRF proof. Research storage uses only `research_*` tables marked `NON_RAB1_RESEARCH_ONLY` and authority effect `NONE`.

Human Access identity is not reused as machine identity. Machine Access alone is insufficient because every request is also HMAC-signed and replay-protected. A network command supplies an action ID only; all executable argv and paths are local reviewed code.

The original Provider Registry, Instrument Master and temporal evidence envelopes remain unchanged. Independent research collectors use Coinbase Exchange, Alpha Vantage, FRED, fixed SEC XBRL Company Concept endpoints and Treasury Fiscal Data on fixed hosts with bounded responses, schemas, quotas, freshness receipts and no generic URL surface.
