# Future Strategy Intake Policy

## Status and purpose

This document defines an intake mechanism only. It is not active research authorization, a candidate-generation brief, or permission to inspect validation or holdout data.

A future proposal may be considered only when supported by genuinely new information, for example an independent academic or professional hypothesis, a new causally available dataset, a forward-observed effect, a materially different market structure or asset class, independently reproduced external evidence, or an externally developed strategy with auditable evidence.

## Mandatory reopening gate

Before implementation or result evaluation, an accepted proposal requires a new versioned reopening contract. Intake acceptance alone cannot authorize research, data acquisition, backtesting, dry-run, live trading, or capital.

The contract and review must include:

1. an overlap audit against every rejected family;
2. an economic rationale and falsifiable mechanism;
3. declared assets, instruments, venue, and timeframe;
4. proof that every input is causally available at the decision timestamp;
5. an immutable protocol locked before outcome-bearing data is inspected;
6. a declared candidate count and total experiment budget;
7. a fixed parameter or hyperparameter budget;
8. certified data and immutable data identities;
9. development-only selection;
10. one fixed validation stage and one sealed holdout;
11. realistic fees plus spread, slippage, market-impact, and latency stress;
12. multiple-testing control and appropriate null controls;
13. concentration, drawdown, and tail-risk controls;
14. independent-engine ledger parity;
15. lookahead analysis and recursive analysis where relevant;
16. a paper-only dry-run stage after research qualification;
17. a separate proof-capital authorization;
18. explicit expiration and invalidation rules;
19. a separate live-trading authorization.

The contract must also state whether model training is allowed, the maximum number of revisions, the consequences of provider or split changes, the treatment of missing data, and the exact rejection rule. A negative result is valid completion.

## Overlap audit

The review compares economic mechanism, inputs, transformations, decision timing, holding period, venue, asset exposure, and payoff structure—not merely names. A proposal that substantially reproduces a rejected family is a reopening of that family and must be rejected at intake unless new evidence and a new contract expressly justify a scientifically distinct test.

## Evaluation sequence

1. Establish novelty and economic rationale without using protected DeltaGrid results as an oracle.
2. Freeze the contract, candidates, data, splits, parameters, costs, and experiment budget.
3. Certify data and causal availability.
4. Select at most the contract-authorized number of candidates on development only.
5. Evaluate the fixed survivor on validation without reselection.
6. Open the sealed holdout once, only if every preceding gate passes.
7. Perform independent-engine parity, lookahead, recursive, stability, and operational checks.
8. If separately authorized, conduct paper-only dry-run evaluation.
9. Seek distinct proof-capital and live-trading authorizations; neither is automatic.

## Prohibited conduct

- Reopening or retuning a rejected Alpha Search A parameter.
- Reopening or retuning a rejected Alpha Search B parameter.
- Relabelling a rejected family to evade the overlap audit.
- Reopening Mission 89 carry or Mission 90 directional hypotheses indirectly.
- Lowering gates after observing failure.
- Changing a provider after failure without a new contract.
- Changing the time split after observing results.
- Reusing or replacing an exposed holdout.
- Hidden candidate generation or undocumented manual exclusion.
- Unlimited parameter, feature, strategy, or model search.
- Repeated rescue cycles not fixed in advance.
- Automatic strategy, dry-run, model, or capital promotion.
- Claiming that backtest profitability proves future profitability.

## Fail-closed outcomes

Missing causal timestamps, unverifiable provenance, excessive overlap, exhausted experiment budget, leakage, unstable results, failed costs, failed replication, failed concentration or drawdown controls, or failed parity rejects or pauses the proposal according to the frozen contract. The gates may not be repaired using later-stage results.

No accepted intake can itself create a profitability claim or authorize capital.
