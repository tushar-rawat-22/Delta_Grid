# M101 handoff binding plan

The Founder preregistration handoff remains authority-zero after trusted-local verification. `npm run plan:m101-binding -- /absolute/path/to/handoff.json` compiles that verified V2 artifact into a deterministic preparation plan. The planner cannot execute Mission 101, Mission 102 or Mission 103 authority operations.

The planner is deliberately narrow. It currently accepts only the reviewed Mission 101 public-market shape used by the active SOL development thesis: Binance public settled one-hour spot OHLCV, with symbols restricted to the canonical Mission 101 set (`BTCUSDT`, `ETHUSDT`, `SOLUSDT`). Unsupported provider, interval, symbol, ambiguous declaration or self-benchmarking input fails closed.

The plan fixes only development intent derivable from founder-authored scientific text. Private custody and authority facts remain unresolved until observed on the trusted local operator boundary, including release/certificate identity, exact chronology and causal cutoff, descriptor location, authority runtime, trial ledger, stable M102 registry/family/variant identity, experiment family, budget, permit expiry, exact M94 reservation/request identity and M103 campaign/program identity.

## Dependency order

The preparation sequence follows the actual authority dependencies rather than treating the missions as independent checkboxes:

1. independently certify the existing forward-custody release read-only;
2. create the exact `REAL_MARKET_DEVELOPMENT` descriptor only through the acknowledged Mission 101 operator boundary;
3. inspect the private authority runtime read-only;
4. initialize that runtime only if absent and only through its explicit acknowledgement;
5. verify the stable Mission 102 registry, family and variant identity before permit issuance, because the Mission 101 permit binds an exact experiment family;
6. issue one finite development permit against the exact repository/dataset/release/family identity;
7. register the finite Mission 94 development budget required by Mission 101 admission;
8. reserve one metadata-only Mission 101 admission, establishing the exact M94 request/reservation and M101 permit-consumption chain;
9. prepare and freeze the pre-result Mission 103 program using the now-existing exact M94/M101 bindings plus stable M102 identities; and
10. separately founder-activate that exact frozen program before any result-bearing execution authority can exist.

Mission 102 result-bearing execution is intentionally outside this plan. Mission 102 requires an already admitted Mission 101 trial. Mission 103 in turn freezes the complete inferential program around exact M94/M101 bindings and stable M102 identities before result inspection. The planner therefore stops before result-bearing Mission 102 execution rather than placing Mission 103 too early or pretending admission itself is execution authority.

The planner cannot execute any of those steps. Its output records `commands_executed: false`, `writes_performed: false`, no descriptor/runtime creation, no permit issue or consumption, no budget registration, no trial reservation/admission, no M103 campaign/program mutation, no result execution, no protected evidence opening, no Mission 104 authority, no trading authority and no capital authority.

This separation lets GitHub-side engineering harden orchestration and dependency validation while private certified custody, permit and trial runtimes stay on the trusted local operator boundary.
