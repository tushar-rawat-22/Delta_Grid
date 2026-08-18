# M101 handoff binding plan

The Founder preregistration handoff remains authority-zero after trusted-local verification. `npm run plan:m101-binding -- /absolute/path/to/handoff.json` compiles that verified V2 artifact into a deterministic Mission 101 preparation plan without executing any Mission 101 command.

The planner is deliberately narrow. It currently accepts only the reviewed Mission 101 public-market shape used by the active SOL development thesis: Binance public settled one-hour spot OHLCV, with symbols restricted to the canonical Mission 101 set (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`). Unsupported provider, interval, symbol, ambiguous declaration, or self-benchmarking input fails closed.

The plan fixes the declared development intent that can be derived from founder-authored scientific text while leaving private runtime facts unresolved. Those unresolved facts include the certified release and certificate identities, exact temporal bounds and causal cutoff, descriptor destination, private authority root, trial ledger, experiment family, budget identity, permit expiry, and later M102/M103 identities.

The deterministic sequence is preparation only:

1. certify the existing forward-custody release read-only;
2. create one exact `REAL_MARKET_DEVELOPMENT` descriptor only through the acknowledged Mission 101 operator boundary;
3. initialize or inspect the private authority runtime;
4. issue one finite development permit only after exact inputs are known;
5. register a finite Mission 94 development budget;
6. verify the sealed Mission 102 family and variant identity;
7. verify the pre-result Mission 103 program identity; and
8. reserve one metadata-only Mission 101 admission only after every prior identity is bound.

The planner cannot execute any of those steps. Its output explicitly records `commands_executed: false`, `writes_performed: false`, no permit issue or consumption, no budget registration, no trial reservation, no admission, no result execution, no protected evidence opening, no Mission 104 authority, no trading authority, and no capital authority.

This separation lets GitHub-hosted development harden the orchestration model while the private certified custody, permit and trial runtimes remain on the trusted local operator boundary.
