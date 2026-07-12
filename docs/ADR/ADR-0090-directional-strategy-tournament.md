# ADR-0090: Directional Strategy Tournament and Charter Lock

Date: 2026-07-12

Status: Accepted after authoritative verification

## Context

Mission 89 rejected and archived the funding-carry hypothesis before validation
or holdout access. The next research branch required a larger economic block,
not another infrastructure-only mission.

Mission 88's execution model represented a two-leg spot/perpetual carry trade.
Reusing that model unchanged for a one-leg directional strategy would have been
incorrect.

## Decision

Mission 90 created a separate assumption-bounded single-leg directional cost
model and ran a development-only tournament containing twelve preregistered
variants across three families. It selected at most one candidate and locked a
fixed Mission 91 charter only when every mandatory gate passed.

Authoritative decision:

`REJECT_ALL_DIRECTIONAL_HYPOTHESES`

Mission 91 status:

`NOT_AUTHORIZED_ALL_DIRECTIONAL_HYPOTHESES_REJECTED`

## Consequences

- Funding carry remains archived.
- Validation and untouched-holdout performance remain unread.
- No second-place fallback may replace a future validation failure.
- No parameter retuning or cost reduction is allowed after selection.
- A rejection or pause is a valid research outcome.
