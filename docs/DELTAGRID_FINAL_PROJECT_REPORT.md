# DeltaGrid Final Project Report

## 1. Document status

This is the final pre-publication project report for the additive DeltaGrid final freeze. It records a completed research platform with no validated profitable strategy. It does not authorize research reopening, paper trading, live trading, orders, or capital deployment.

The Alpha Search B publication commit `a31f4da4fc8b52ca2fa6aaad697350d6e9180736` is the research-closure base. A future final-freeze publication commit does not yet exist and is not asserted here.

## 2. Scope and evidence standard

This report distinguishes three evidence classes:

**A. Committed controlling evidence.** Facts supported by tracked contracts, evidence JSON, reports, tests, implementations, checksum manifests, and Git identities at the research-closure base.

**B. Current final-freeze verification.** Facts produced by the current candidate's compilation, tests, checksum validation, diff review, and scope checks. These are recorded in `docs/evidence/deltagrid_final_freeze/FINAL_FREEZE_VERIFICATION.json` and do not rewrite Class A.

**C. Operator-reported publication metadata.** Context supplied outside committed evidence. Class C is omitted from controlling identities and conclusions. The final project conclusion does not depend on it.

Requested values absent from controlling evidence are not inferred. Where a requested metric is unavailable, this report says: **Not recorded in the controlling evidence.**

## 3. Executive summary

DeltaGrid evolved from a trading-bot concept into a falsification-first quantitative research platform. It built deterministic data, simulation, cost, risk, statistical, evidence, and safety controls. Those controls successfully prevented unsupported promotion: synthetic candidates were not mistaken for real-data alpha, funding carry and directional families were rejected, Alpha Search A stopped at causal data feasibility, and Alpha Search B rejected all four candidates in development.

The final result is scientifically useful but commercially negative: no validated profitable strategy exists. Remaining authorized alpha-family count is zero. Validation and holdout remained closed for Alpha Search B. No current Freqtrade translation, dry-run, live trading, or capital deployment is authorized.

## 4. Original objective

Early repository records describe a research-first execution and risk system intended to progress through local tests, simulations, paper-only controls, and promotion gates before any real capital. Later governance sharpened that objective: find one robust, implementable after-cost edge or stop alpha discovery. Repository growth and test count were explicitly rejected as substitutes for qualified alpha.

## 5. Evolution from trading-bot concept to falsification platform

The early roadmap included monitoring, local simulation, strategy research, paper evidence, autonomous policy concepts, and possible offline learning. Mission 84 demonstrated why pipeline completion is not equivalent to deployable alpha. The product reset then retired open-ended mission numbering, limited the final research budget to two families, prohibited rescue cycles, and made a negative result valid completion.

The final architecture therefore treats rejection as a first-class output. Strategy code is downstream of evidence qualification, not the default deliverable.

## 6. Final architecture

The repository contains five interacting layers:

1. **Governance:** versioned contracts, safety invariants, research policy, decision records, and the additive final-freeze contract.
2. **Data:** schemas, public-data acquisition, provenance, certification, chronological splits, and ignored raw-data boundaries.
3. **Research:** feature engines, strategy laboratories, simulators, walk-forward and null-control machinery, and candidate gates.
4. **Risk and execution:** costs, slippage assumptions, latency, stops, liquidation controls, drawdown limits, position authority, and capital boundaries.
5. **Evidence and QA:** SQLite evidence in historical components, tracked JSON reports, checksums, deterministic tests, and publication verification.

Historical Solidity contracts provide executor, registry, oracle, and risk-guard components. Their existence is not a current deployment authorization.

## 7. Data foundation

DeltaGrid developed market schemas and historical ingestion before the final research programs. Mission 86 implemented a mission-specific public Binance data layer for BTCUSDT, ETHUSDT, and SOLUSDT covering spot OHLCV, perpetual OHLCV, mark price, index price, and settled funding. It preserved raw responses outside tracked source, normalized records, request provenance, hashes, resumable pagination, coverage, and a deterministic manifest.

Alpha Search B later used official Binance monthly one-minute spot-kline archives and checksums for the same three symbols. The source was defined as aggregated trade-flow proxies, not order-book imbalance, queue imbalance, complete order flow, or maker-fill evidence.

## 8. Research and simulation engine

The off-chain research code includes historical backtest frameworks, strategy labs, walk-forward tools, candidate ranking, null and robustness controls, and Alpha Search B-specific foundation, feature, and simulator modules. Alpha Search B used completed-minute causal features, trailing 43,200-minute windows excluding the current minute, strict nearest-rank thresholds, no interpolation or backfill, delayed entries, one position, and a post-exit cooldown.

Simulation output is evidence about the frozen historical experiment. It is not a live signal or forecast.

## 9. Execution-cost model

Mission 88 created `mission88-assumption-bounded-execution-cost-v1`, with three symbols, three scenarios, three notional bands, and 27 profiles. The committed report records modeled costs from 50 to 775 basis points on pair notional. It explicitly lacks historical order-book depth, queue position, true fill latency, and measured market impact, so it makes no order-book precision claim.

Alpha Search B used a separate single-leg cost-attribution contract. Normal, conservative, and severe round-trip costs were locked by pair, split across entry and exit, with scenario timing offsets and latency displacement. Conservative results controlled qualification; severe results were diagnostic.

## 10. Risk model

Historical risk components include drawdown controls, volatility targeting, leverage and liquidation analysis, kill switches, and paper-only governance. Alpha Search B froze spot long-or-cash operation, leverage one, one global position, a 1.5% protective stop, a 24-hour cooldown, a $100 proof wallet, $0.50 planned risk, an $80 deployed-capital ceiling, at least $20 cash reserve, and Decimal downward sizing.

These were research constraints. No proof capital was authorized because no candidate qualified.

## 11. Statistical controls

The final programs used chronological stages, frozen candidate counts, fixed parameters, costs, sample floors, calendar distribution, drawdown and concentration gates, replication, removal diagnostics, and no post-result gate relaxation. Alpha Search B additionally used 5,000 deterministic frequency-matched null repetitions per candidate and Holm adjustment across the four-candidate family.

Development selection could choose at most one candidate. Validation could not reselect. Holdout access was limited to one only after preceding qualification. No candidate reached those later stages.

## 12. Evidence and governance model

Historical records are append-only decision evidence. Contracts lock questions and rules; tracked evidence records outcomes and identities; checksum manifests detect drift; tests reproduce canonical hashes and safety invariants. The product reset is controlling for finite research scope, and the final-freeze contract adds closure without mutating it.

Documentation correction remains possible only for demonstrable factual error and cannot silently change a historical outcome, metric, protocol, hash, decision, or access boundary.

## 13. Early research and safety infrastructure

The repository's early missions built local monitoring, market schemas, route and price simulators, opportunity detection, risk engines, strategy validation, funding research, paper ledgers, observation analytics, research boards, autonomous paper-only gates, and offline-learning governance. Many components use historical names expressing ambitious design intent. Their existence does not establish performance, readiness, or authorization.

The persistent safety boundary was no private execution, no real orders, and no capital before explicit gates.

## 14. Mission 84 synthetic research closure

Missions 84.5 through 84.8 created deterministic synthetic-fixture benchmark, multi-strategy backtest, expanding-window robustness, and candidate-promotion infrastructure. The authoritative closure retained 35 records as `FIXTURE_SCREENING_RECORD_ONLY_NOT_REAL_DATA_VALIDATED`.

Real-data validated candidates, model-training eligible candidates, model promotions, live signals, exchange orders, capital deployments, and profitability claims were all zero. Mission 84 closed as `SYNTHETIC_RESEARCH_PIPELINE_COMPLETE_NO_VALIDATED_ALPHA`.

## 15. Mission 85 research-charter lock

Mission 85 retired the earlier unbuilt model-promotion concept and locked a falsification-first, fully collateralized long-spot/short-perpetual funding-carry hypothesis. It fixed Binance public data, three symbols, five required streams, 12 parameter variants, chronological development/validation/holdout splits, conservative costs, and rejection rules. ML rescue, live trading, orders, and capital were prohibited.

## 16. Mission 86 real-market data foundation

Mission 86 implemented collection and provenance only. It did not authorize backtesting, performance evaluation, model training, signal generation, orders, capital, or profitability analysis. Its outputs remained `UNCERTIFIED_PENDING_MISSION87` until certification.

## 17. Mission 87 dataset certification

The `mission87-final-check` record certified 12 bar series and three funding series, with 276 raw responses, 262,656 market bars, and 8,208 funding observations verified. Twenty-three quality checks passed and none failed. The untouched holdout received structural quality checks only; no holdout performance was evaluated.

## 18. Mission 88 execution-cost model

Mission 88 completed 24 checks with no recorded failure and approved its assumption-bounded model for baseline falsification with uncertainty. It read zero market-data rows during cost-model generation and performed no strategy backtest or profitability analysis. Its two-leg methodology was not misrepresented as measured single-leg directional microstructure.

## 19. Mission 89 funding/basis-carry rejection

Mission 89 evaluated 12 development variants and found no development candidate. Its decision was `REJECT_AND_ARCHIVE_FUNDING_CARRY`. Validation closed positions and holdout rows read were both zero. The single mandatory candidate-existence gate failed, so Mission 90 holdout work for carry was not authorized.

## 20. Mission 90 directional-tournament rejection

Mission 90 preregistered 12 variants across spot trend, perpetual trend, and volatility breakout. It recorded 108 variant/scenario/NAV evaluations on development data, zero eligible candidates, zero validation rows, and zero holdout rows. The decision was `REJECT_ALL_DIRECTIONAL_HYPOTHESES`.

No live signal, order, capital deployment, model, or profitability claim was produced.

## 21. Historical Freqtrade hybrid and parity boundary

The product-reset record describes a pinned and parity-verified historical Freqtrade runtime and requires exact Freqtrade ledger parity for a future qualified candidate. Historical hybrid concepts also required validated standalone components.

This infrastructure history does not authorize a current strategy. Alpha Search B never qualified for Freqtrade translation. Current Freqtrade dry-run, live trading, and capital deployment remain unauthorized.

## 22. Product reset

The reset changed governance from open-ended repository growth to a finite money-first alpha-validation program. It authorized two final economic families, four variants per family, at most one selected candidate, zero rescue cycles, no post-result threshold relaxation, and explicit stop conditions. Both families are now rejected, so the reset's next action is to freeze DeltaGrid as a completed research platform.

## 23. Retirement of open-ended mission numbering

The product-reset contract records `mission_numbering: RETIRED`. Future work is not another implied numbered mission. It requires an explicit versioned reopening contract tied to genuinely new information and a bounded experiment.

## 24. Alpha Search A hypothesis and rejection

Alpha Search A asked whether lagged macro risk conditions could improve low-turnover BTC spot long-or-cash outcomes after realistic costs. Its required inputs included SP500, VIXCLS, DTWEXBGS, and DGS10 with at least a 24-hour information delay.

The frozen feasibility protocol could not establish the required causal first-availability evidence for SP500. The program stopped as `REJECTED_BEFORE_STRATEGY_BUILD`. It accessed no BTC archives or price/return fields, built no strategy, evaluated no signal or P&L, and opened neither validation nor holdout. The rejection makes no conclusion about whether macro regimes can predict BTC.

## 25. Alpha Search B protocol

Alpha Search B asked whether public, causally available spot aggregated-trade-flow information could produce a robust long-or-cash edge after costs, latency, and multiple-testing control. Four candidates were frozen:

- `BTC_SELF_FLOW_PERSISTENCE_60M`
- `BTC_SELF_FLOW_PERSISTENCE_120M`
- `BTC_FLOW_LEADS_ETH_60M`
- `BTC_FLOW_LEADS_SOL_60M`

No price-return entry threshold, mean reversion, breakout, market making, maker-fill assumption, or ML was authorized.

## 26. Alpha Search B data acquisition and certification

The committed acquisition manifest expects 75 official archives. The prohibited-access audit records 75 public archive GETs, 75 public checksum GETs, one public exchange-information GET, and one public reference-price GET, with zero validation URL, holdout URL, account, credential, private-endpoint, or order requests.

Certification records continuous synchronized minutes, duplicate and gap checks, timestamp-unit handling, processed identities, and causal data coverage. Raw and processed paths remain ignored and outside Git. Alpha Search B acquisition and development publication recorded zero validation and holdout access.

## 27. Alpha Search B feature engine

The feature engine used taker-buy quote-volume ratio, quote volume, trade count, and positive BTC-minus-target taker-buy-ratio gaps. Each threshold used only prior completed minutes, required at least 90% coverage, excluded the signal minute, and used strict nearest-rank comparisons. Zero denominators were ineligible, and backfill or interpolation was prohibited.

## 28. Alpha Search B simulator

Candidates were evaluated independently. Entry occurred one, two, or three minutes after the completed signal minute for normal, conservative, or severe scenarios. Holding time began at actual entry. A protective-stop breach exited at the following minute open no better than the stop barrier; missing required minutes invalidated the trade and data gate.

Signals while a position was open or during the 24-hour cooldown were rejected and counted. No result-based signal ranking or monthly trade target was used.

## 29. Alpha Search B candidate-level results

The table reports the controlling conservative development scenario. Net result is scenario net profit after costs; drawdown is maximum marked-to-market drawdown.

| Candidate | Development observations or trades | Net result | Drawdown | Replication | Null/Holm result | Final decision |
|---|---:|---:|---:|---|---|---|
| `BTC_SELF_FLOW_PERSISTENCE_60M` | 227 trades | -20.7017875081200 | 20.701787508120006% | Failed | Holm-adjusted p = 1.0; failed | Rejected in development |
| `BTC_SELF_FLOW_PERSISTENCE_120M` | 218 trades | -21.2115871703000 | 21.462638507050137% | Failed | Holm-adjusted p = 1.0; failed | Rejected in development |
| `BTC_FLOW_LEADS_ETH_60M` | 14 trades | -0.9213430000 | 1.4747805617959513% | Failed | Holm-adjusted p = 0.8782243551289743; failed | Rejected in development |
| `BTC_FLOW_LEADS_SOL_60M` | 15 trades | -0.0853141960 | 1.1580506702039948% | Failed | Holm-adjusted p = 0.1943611277744451; failed | Rejected in development |

All four failed required gates; `selected_candidate` is `null`.

## 30. Null controls

Each candidate used 5,000 deterministic placebo repetitions stratified by target pair, calendar month, and UTC hour. Sampling preserved the candidate's completed-trade frequency and applied unchanged timing, stop, scenario cost, one-position, and cooldown rules. Construction failure was itself a rejection condition.

No candidate achieved the required adjusted one-sided p-value below 0.05.

## 31. Holm multiple-testing adjustment

The four raw p-values were adjusted as one family of size four. Adjusted values were 1.0 for both self-flow candidates, 0.8782243551289743 for BTC-leading-ETH, and 0.1943611277744451 for BTC-leading-SOL. The adjustment prevented selection from treating the best of four searches as an isolated test.

## 32. Replication analysis

Replication could not select or rescue a candidate and used unchanged parameters on the protocol-declared assets. At least one conservative-positive replication asset was required. Every candidate's `replication_pass` was false, so replication provided no promotion path.

## 33. P&L attribution

Tracked attribution separates gross profit, gross loss, net profit, expectancy, winner and loser statistics, monthly and quarterly net results, removal diagnostics, tail statistics, and marked-to-market drawdown for normal, conservative, and severe scenarios. Promotion metrics are net after scenario costs; gross P&L is attribution-only except for the defined retention diagnostic.

## 34. Cost attribution

The cost contract attributes authoritative pair/scenario totals to fee and spread/slippage components and reports latency displacement separately. The controlling cost identity is the file SHA-256 of `contracts/ALPHA_SEARCH_B_COST_ATTRIBUTION_V1.json`. Costs were not reduced after results, and conservative costs controlled qualification.

## 35. Concentration and drawdown controls

Development required at least five positive quarters, positive-quarter concentration no greater than 35%, top-one-percent winner concentration below 25%, robustness after removing the best month and five largest winners, and drawdown no greater than 10%. The sparse cross-asset candidates failed sample, calendar, concentration, and other gates. Both self-flow candidates exceeded the 10% conservative drawdown limit and recorded no positive quarter.

## 36. Final Alpha Search B development decision

The decision is `ALPHA_SEARCH_B_REJECTED_DEVELOPMENT`. No candidate was selected. Validation and holdout performance were not accessed. Freqtrade translation, dry-run, live trading, and capital deployment were false. No replacement or rescue family was authorized.

## 37. Final research status

- Project: `COMPLETED_RESEARCH_PLATFORM_NO_VALIDATED_ALPHA`
- Alpha discovery: `STOPPED_ALL_AUTHORIZED_FAMILIES_REJECTED`
- Validated profitable strategy: `false`
- Remaining authorized families: `0`
- Infrastructure freeze: `ACTIVE`
- Mission numbering: retired
- Profitability claim: prohibited

## 38. Final reported repository state

The committed pre-freeze Alpha Search B/reset focused baseline is 37 passed. The committed complete off-chain baseline is 715 passed with one third-party `websockets.legacy` deprecation warning. These historical values are not represented as current post-change totals.

Current final-freeze compilation, focused-test, full-suite, checksum, diff, scope, raw-tracking, and credential-scan results are Class B evidence in `FINAL_FREEZE_VERIFICATION.json`.

## 39. Strategy-family outcome table

| Research family | Controlling outcome | Later-stage access or authorization |
|---|---|---|
| Mission 84 synthetic research | Pipeline complete; no real-data validated alpha | No model training or promotion |
| Funding and basis carry | Rejected and archived | Holdout rows 0 |
| Conventional directional strategies | All hypotheses rejected | Validation rows 0; holdout rows 0 |
| Static intraday session exposure | Rejected in product reset | Frozen |
| Alpha Search A macro risk regime | Rejected before strategy build | No P&L, validation, or holdout |
| Alpha Search B microstructure liquidity state | Rejected in development | Selected candidate null; validation 0; holdout 0; no translation or trading |

## 40. What DeltaGrid proved

DeltaGrid proved that its repository can encode finite hypotheses, causal and chronological boundaries, data identities, cost and risk assumptions, deterministic simulation, null and multiple-testing controls, negative decisions, checksum manifests, and fail-closed authorization. It proved that the governed process could stop instead of promoting an unsupported candidate.

## 41. What DeltaGrid did not prove

It did not prove a profitable strategy, future profitability, execution quality in live markets, market-impact precision, robustness outside tested assets and periods, or current operational readiness. It did not prove that ML can discover alpha. It did not authorize live trading or capital.

## 42. Engineering lessons

Deterministic contracts should hash a canonical payload excluding their own hash field. Publication manifests must not include themselves. Permanent tests should verify durable repository content, not current HEAD, branch, staging, or dirty-worktree state. Candidate scope checks belong to pre-publication evidence, while post-commit tests must remain valid on a clean tree.

## 43. Scientific lessons

Causal availability can reject a program before strategy code. Costs can reverse attractive gross results. Sparse samples and concentration can invalidate positive-looking outcomes. Multiple-testing correction and null controls matter when several candidates share one search budget. Protected later stages should remain unopened when development fails.

## 44. Product and business lessons

A large platform is not a product with validated economic value. Honest negative closure is more credible than describing infrastructure as performance. Any future commercial claim must follow evidence, not repository size, automation, model branding, or test count. Small proof capital is an operational verification concept, not an income promise.

## 45. Security and operational limitations

The final-freeze task uses no network, credentials, order endpoints, validation URLs, holdout URLs, or raw ignored data. That scoped verification does not prove that no secret or network activity has ever existed across the machine's lifetime. Historical data acquisition used public endpoints under its own recorded audit.

The platform lacks current live venue integration authority, demonstrated production recovery, measured order-book impact, and an approved strategy. Private execution remains outside the final state.

## 46. Present platform capabilities

Present capabilities include local deterministic research contracts, schemas, public-data provenance, dataset certification, simulations, execution-cost assumptions, risk controls, chronological evaluation, statistical falsification, tracked evidence, manifests, and regression tests. These can support a carefully contracted future hypothesis without reopening rejected work.

## 47. Current limitations

No validated alpha exists. All authorized families are exhausted. Alpha Search B validation and holdout remain sealed. Costs and impact retain model uncertainty. Evidence covers declared scopes rather than universal market or machine history. The repository is a research platform, not a current trading service.

## 48. Future-strategy intake

`docs/FUTURE_STRATEGY_INTAKE_POLICY.md` allows intake only for genuinely new information. It requires novelty and overlap review, causal proof, a new versioned reopening contract, fixed candidates and experiment budget, certified data, chronological development/validation/holdout stages, costs and stress, multiple-testing and risk controls, independent parity, paper-only evaluation, expiration, and separate capital and live authorizations.

Intake is not research authorization.

## 49. Possible future ML research

`DELTAGRID_ML_RESEARCH_ADAPTER` is documented but unauthorized. A future contract may consider small fixed supervised tabular models and simple baselines under rolling or expanding chronological evaluation, purging, gap or embargo for overlapping labels, fixed seeds and budgets, ablations, stability, drift, expiration, realistic costs, and separate promotion boundaries.

ML may produce forecasts or candidate evidence. It may not use Alpha A or B outcomes as a search oracle, promote itself, authorize FreqAI, trade, or authorize capital.

## 50. Final conclusion

DeltaGrid completed its authorized research mission without finding validated alpha. That is the correct recorded outcome. The platform and all negative evidence are preserved; research, ML, Freqtrade translation, dry-run, live trading, and capital remain closed. Future work requires a genuinely new hypothesis and an explicit new versioned reopening contract.

## 51. Reproducibility appendix

The final-freeze contract uses the repository's canonical JSON method: UTF-8 JSON with sorted keys, compact separators, ASCII escaping, and `contract_hash_sha256` excluded from the hashed payload. The closure checksum manifest contains ordinary SHA-256 hashes for the eight specified files and excludes itself.

The permanent closure test resolves paths relative to the repository, avoids current HEAD and branch assertions, reproduces controlling identities, verifies required prose and evidence scope, checks the manifest, and verifies with `git ls-files` that no Alpha Search B raw data is tracked.

## 52. Repository-navigation appendix

- `README.md` — public closure and navigation
- `contracts/DELTAGRID_FINAL_FREEZE_V1.json` — additive closure contract
- `docs/DELTAGRID_FINAL_FREEZE.md` — freeze rationale and authority
- `docs/FUTURE_STRATEGY_INTAKE_POLICY.md` — future intake gate
- `docs/DELTAGRID_ML_RESEARCH_ADAPTER.md` — possible ML design policy
- `docs/DELTAGRID_PRODUCT_RESET.md` — finite research reset
- `docs/ALPHA_SEARCH_A_REJECTION.md` — Alpha A decision
- `docs/ALPHA_SEARCH_B_PROTOCOL.md` — Alpha B protocol
- `docs/evidence/alpha_search_b_development/` — Alpha B tracked publication evidence
- `docs/evidence/deltagrid_final_freeze/` — current final-freeze verification and manifest
- `offchain/tests/test_deltagrid_final_freeze.py` — permanent closure tests

## 53. Controlling-contract and evidence appendix

Primary controlling records include:

- `contracts/DELTAGRID_PRODUCT_RESET_V1.json`
- `contracts/ALPHA_SEARCH_A_REJECTION_V1.json`
- `contracts/ALPHA_SEARCH_B_PROTOCOL_V1.json`
- `contracts/ALPHA_SEARCH_B_COST_ATTRIBUTION_V1.json`
- `docs/evidence/alpha_search_a_feasibility/FEASIBILITY_REJECTION.json`
- `docs/evidence/alpha_search_b_development/DEVELOPMENT_DECISION.json`
- `docs/evidence/alpha_search_b_development/CANDIDATE_DEVELOPMENT_RESULTS.json`
- `docs/evidence/alpha_search_b_development/NULL_CONTROL_RESULTS.json`
- `docs/evidence/alpha_search_b_development/HOLM_ADJUSTMENT.json`
- `docs/evidence/alpha_search_b_development/REPLICATION_RESULTS.json`
- `docs/evidence/alpha_search_b_development/PNL_ATTRIBUTION.json`
- `docs/evidence/alpha_search_b_development/PROHIBITED_ACCESS_AUDIT.json`
- Mission 84 closure implementation, tests, and source-of-truth documentation
- Mission 85, 89, and 90 versioned contracts and Mission 89/90 reports
- Mission 86–88 implementations, tests, and committed project records

## 54. Controlling-hash appendix

| Identity | Type | SHA-256 |
|---|---|---|
| Alpha Search B protocol | Canonical payload identity embedded in contract | `ee82fdb3758028cfa6455ffa610cbff46855890ded65cc2175801897fe509469` |
| Alpha Search B cost attribution | File SHA-256 | `e102f6aa21f83dfdc05090411c790f1d2ed2803d02f310fb3289e67c2790165c` |
| Alpha Search B development decision | File SHA-256 | `3aa332f04287e55d8ceefeb7d19b2265363f70a703bda2cc98efab85f1f2984a` |
| Alpha Search B prohibited-access audit | File SHA-256 | `9d25db64ce691d1d04903849237331a938ecbfdf31877a00a1c3f43155e21ed1` |
| DeltaGrid final-freeze contract | Canonical payload identity excluding hash field | `16cdf1244f270b6484af8d778b3a2359cab9ec401784d443d64c86c019497338` |

Ignored-artifact count and tree metadata are not controlling identities and are intentionally omitted.
