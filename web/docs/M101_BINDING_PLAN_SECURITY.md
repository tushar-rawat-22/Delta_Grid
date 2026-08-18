# M101 binding planner security properties

The binding planner is intentionally not an operator or execution surface.

It may read exactly one already verified Founder preregistration handoff file, re-check the handoff identity against the trusted-local verifier, parse the embedded canonical review, and derive only the narrow Mission 101 development intent that is explicit in the preregistered text.

It has no network client, database binding, subprocess launcher, Wrangler integration, filesystem writer, permit issuer, budget registrar, admission path, result runner, protected-evidence reader, exchange credential, order path, or capital authority.

If the handoff declares an unsupported provider, interval, symbol, ambiguous Instrument/Benchmark line, or the same instrument and benchmark, planning fails closed. Private custody/runtime values remain unresolved until observed on the trusted local operator boundary.

The planner therefore reduces operator ambiguity without converting a Founder-authored hypothesis into research authority.
