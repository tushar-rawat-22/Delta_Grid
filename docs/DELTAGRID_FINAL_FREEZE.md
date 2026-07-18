# DeltaGrid Final Freeze

## Status

DeltaGrid is frozen as `COMPLETED_RESEARCH_PLATFORM_NO_VALIDATED_ALPHA`. It has no validated profitable strategy and no authority for dry-run, live trading, orders, or capital deployment.

## Why the project is frozen

The product reset authorized exactly two final economic-information families. Alpha Search A stopped before strategy construction when its frozen causal data-feasibility requirement could not be met. Alpha Search B evaluated all four authorized candidates on development data and rejected every candidate. The remaining authorized family count is therefore zero, and alpha discovery is `STOPPED_ALL_AUTHORIZED_FAMILIES_REJECTED`.

Continuing without a new information source and a new contract would turn a finite falsification program into an open-ended search over failed evidence. The freeze preserves the scientific value of stopping.

## Present research status

- Validated profitable strategy: `false`
- Alpha Search A: `REJECTED_BEFORE_STRATEGY_BUILD`
- Alpha Search B: `ALPHA_SEARCH_B_REJECTED_DEVELOPMENT`
- Selected Alpha Search B candidate: `null`
- Alpha Search B validation access: `0`
- Alpha Search B holdout access: `0`
- Remaining authorized alpha families: `0`
- Infrastructure freeze: `ACTIVE`
- Open-ended mission numbering: retired

The access counts above are scoped to the Alpha Search B acquisition and development publication. They are not a universal audit of every activity across DeltaGrid's lifetime.

## Why negative results are preserved

Negative results prevent the same evidence from being repeatedly optimized until it appears favorable. They document which economic mechanisms, data assumptions, costs, sample gates, null controls, and robustness checks failed. Rewriting or deleting them would destroy the decision lineage needed by future reviewers.

Alpha Search A cannot be rescued by changing provider, series, release timing, samples, or thresholds after the feasibility failure. Alpha Search B cannot be rescued by changing parameters, adding candidates, relaxing gates, relabelling the family, or substituting a new family after observing development results. Both programs explicitly authorized zero rescue cycles.

Mission 89's funding/basis-carry rejection and Mission 90's directional-tournament rejection also remain closed. A renamed or combined strategy may not reopen either family indirectly; future intake must perform an overlap audit against their economic mechanisms and signal construction.

## Platform capability is not alpha

DeltaGrid contains substantial data, simulation, cost, risk, evidence, and governance infrastructure. Those components can make research more reproducible and safer, but they cannot create an economic edge. Passing tests shows that specified software and documentation invariants hold; it does not show that a strategy earns money now or in the future.

## Validation and holdout discipline

Alpha Search B stopped in development because no candidate qualified. Validation and holdout remain closed. Opening them after development rejection would spend protected evidence without an eligible candidate and would invite selection on out-of-sample results.

## Historical Freqtrade boundary

The product-reset record documents a historical pinned and parity-verified Freqtrade runtime and specifies exact ledger parity as a possible future promotion gate. This does not authorize an implementation now. No Alpha Search B candidate was authorized for Freqtrade translation. No Freqtrade dry-run, live trading, or capital deployment is currently authorized.

## Authorized now

- Review and publication of the additive final-freeze candidate by an external maintainer.
- Read-only use of committed research documentation and evidence.
- Demonstrable factual documentation corrections under the correction policy below.
- Critical correctness or dependency work only through the controlling historical governance and any required new authorization.
- Intake review of genuinely new future information without beginning strategy research.

## Prohibited now

- Strategy construction, optimization, rescue, replacement, or candidate generation.
- Validation or holdout access.
- New backtests, ML training, Freqtrade or FreqAI translation, paper trading, dry-run, live trading, orders, or capital.
- Lowering gates or changing providers, time splits, costs, or parameters in response to failure.
- Treating synthetic evidence, passing tests, statistical significance, or infrastructure maturity as profitability.

## Conditions for future reopening

Future strategy research requires genuinely new information, a documented overlap audit, and an explicit new versioned reopening contract. That contract must freeze the economic rationale, data availability, assets, venue, time split, candidates, experiment budget, costs, statistical controls, validation, one sealed holdout, parity, paper-only boundary, expiration rules, and separate capital and live-trading gates before result-guided work begins.

Possible future ML research is governed by the same rule. This closure documents an adapter policy but does not authorize implementation, training, evaluation, FreqAI use, or model promotion.

## Contract role

`contracts/DELTAGRID_FINAL_FREEZE_V1.json` is the deterministic additive closure contract. Its canonical payload hash excludes `contract_hash_sha256`, following the repository convention and avoiding a self-referential hash. It references the Alpha Search B publication commit as the research-closure base; it does not name a future final-freeze publication commit or constrain future HEADs.

The contract cannot silently supersede historical contracts. A future reopening contract may change what work is authorized prospectively, but it may not rewrite a prior outcome, metric, protocol, identity, or access record.

## Documentation correction policy

Repository documentation may later be corrected for demonstrable factual errors, but research or trading capability work requires an explicit new versioned reopening contract.

A documentation correction must not silently change a historical research outcome, metric, protocol, hash, decision, access count, or authorization boundary. Corrections should identify their evidence and preserve the old decision lineage.

## No implicit authorization

This closure does not authorize ML research, model training, paper trading, dry-run, live trading, orders, Freqtrade/FreqAI implementation, or capital. Each remains false unless a future versioned contract and the subsequent stage-specific evidence explicitly authorize it.
