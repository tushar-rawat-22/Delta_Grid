# Alpha Search B

> **Explanatory summary**
>
> This page explains preserved DeltaGrid research and evidence for human
> readers. It does not replace the linked source records, change their results,
> reopen research, or authorize paper trading, live trading, capital deployment,
> ML, or autonomous execution.

## What this record covers

Alpha Search B was the final authorized economic family. Its protocol was
frozen before evaluation, then four spot aggregated-trade-flow candidates were
assessed using development data only.

## Question investigated

The search asked whether public, causally available spot aggregated-trade-flow
information could produce a robust long-or-cash edge after realistic costs,
latency, and multiple-testing controls.

## Evidence and controls

The evidence package includes acquisition and certification manifests, causal
feature and simulator identities, candidate ledgers, P&L and cost attribution,
frequency-matched null controls, Holm multiple-testing adjustment, unchanged
replication tests, and focused and regression test records. The prohibited-
access audit records zero validation URL, holdout URL, account, credential,
private-endpoint, and order requests.

Raw performance and cost-adjusted performance have distinct roles. The P&L
record reports gross profit and loss separately for attribution. Qualification
uses scenario net results after fees and spread/slippage costs; conservative
costs control promotion, while severe costs are diagnostic. Statistical
adjustment then treats all four candidates as one search family, and replication
tests unchanged logic on the declared assets without selecting or rescuing a
candidate.

The controlling conservative development results were:

| Candidate | Trades | Conservative net result | Holm-adjusted p-value | Replication |
|---|---:|---:|---:|---|
| `BTC_SELF_FLOW_PERSISTENCE_60M` | 227 | `-20.7017875081200` | `1.0` | Failed |
| `BTC_SELF_FLOW_PERSISTENCE_120M` | 218 | `-21.2115871703000` | `1.0` | Failed |
| `BTC_FLOW_LEADS_ETH_60M` | 14 | `-0.9213430000` | `0.8782243551289743` | Failed |
| `BTC_FLOW_LEADS_SOL_60M` | 15 | `-0.0853141960` | `0.1943611277744451` | Failed |

One candidate had positive normal-scenario net profit but negative conservative
net profit. That raw-looking favorable case did not satisfy the controlling
cost scenario, sample, calendar, concentration, statistical, and replication
gates. Metrics from different candidates or scenarios are not averaged here.

## Result

All four candidates were rejected in development. The machine decision
`ALPHA_SEARCH_B_REJECTED_DEVELOPMENT` means no candidate advanced. Validation
and holdout performance remained sealed, and the selected candidate is `null`.

## Why it matters

The negative development result demonstrates that the frozen controls prevented
a sparse or favorable-looking partial result from being promoted. Costs, null
controls, multiple-testing adjustment, replication, concentration, and protected
later-stage data all retained their intended roles.

## What this does not authorize

The result authorizes no replacement, rescue, validation or holdout access,
Freqtrade translation, dry-run, paper trading, live trading, capital, ML, or
autonomous execution. The [final freeze](../DELTAGRID_FINAL_FREEZE.md) controls
current authorization.

Exact source records control precise values and historical wording. Any
discrepancy must be resolved in favor of the source record, not this summary.

## Source records

- [Alpha Search B protocol](../ALPHA_SEARCH_B_PROTOCOL.md)
- [Alpha Search B development decision](../evidence/alpha_search_b_development/DEVELOPMENT_DECISION.md)
- [Alpha Search B protocol contract](../../contracts/ALPHA_SEARCH_B_PROTOCOL_V1.json)
- [Alpha Search B cost-attribution contract](../../contracts/ALPHA_SEARCH_B_COST_ATTRIBUTION_V1.json)
- [Candidate development results](../evidence/alpha_search_b_development/CANDIDATE_DEVELOPMENT_RESULTS.json)
- [Cost attribution](../evidence/alpha_search_b_development/COST_ATTRIBUTION.json)
- [Data acquisition manifest](../evidence/alpha_search_b_development/DATA_ACQUISITION_MANIFEST.json)
- [Data certification](../evidence/alpha_search_b_development/DATA_CERTIFICATION.json)
- [Machine development decision](../evidence/alpha_search_b_development/DEVELOPMENT_DECISION.json)
- [Feature-engine manifest](../evidence/alpha_search_b_development/FEATURE_ENGINE_MANIFEST.json)
- [Holm adjustment](../evidence/alpha_search_b_development/HOLM_ADJUSTMENT.json)
- [Null-control results](../evidence/alpha_search_b_development/NULL_CONTROL_RESULTS.json)
- [P&L attribution](../evidence/alpha_search_b_development/PNL_ATTRIBUTION.json)
- [Prohibited-access audit](../evidence/alpha_search_b_development/PROHIBITED_ACCESS_AUDIT.json)
- [Replication results](../evidence/alpha_search_b_development/REPLICATION_RESULTS.json)
- [Simulator manifest](../evidence/alpha_search_b_development/SIMULATOR_MANIFEST.json)
- [Test results](../evidence/alpha_search_b_development/TEST_RESULTS.json)
