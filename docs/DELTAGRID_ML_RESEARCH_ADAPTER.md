# DELTAGRID_ML_RESEARCH_ADAPTER

## Policy status

`DELTAGRID_ML_RESEARCH_ADAPTER` is a possible future component described as design policy only. Its status is `DOCUMENTED_NOT_AUTHORIZED`. No implementation, model training, evaluation, model artifact, FreqAI strategy, trading action, or capital authorization is created by this document.

## Governing principle

Machine learning may generate forecasts or candidate evidence. It may not promote itself, authorize trading, or authorize capital.

## Recommended initial scope

If a future versioned reopening contract authorizes work, the initial scope should be supervised tabular classification or regression, a small fixed model family, and simple statistical baselines. Reinforcement learning, autonomous LLM trading agents, unrestricted strategy-generation loops, and AI-controlled repeated rescue cycles should remain prohibited initially.

## Mandatory future contract

A future ML reopening contract must freeze before result-guided work:

- economic question, prediction target, label definition, and prediction horizon;
- feature definitions and feature-availability timestamps;
- assets, venues, timeframe, and execution timing;
- training, inference, validation, and sealed-holdout windows;
- purging policy and gap or embargo policy;
- retraining cadence;
- model families and fixed hyperparameter budget;
- total experiment budget and random seeds;
- baseline models and calibration method;
- decision thresholds and cost assumptions;
- multiple-testing adjustment;
- feature-ablation, seed-stability, and regime-stability requirements;
- data, model, and prediction identities;
- drift monitoring, model expiration, promotion gates, and rejection gates;
- paper-trading boundary and separate capital-authorization boundary.

## Causal construction

Future information may appear only in target labels inside the appropriate training construction. Input features may use only information available at the decision time. The data pipeline must preserve source timestamps, first-availability timestamps, transformation timing, and the execution delay used by the simulator.

Authoritative random train/test splitting is prohibited for financial time-series evaluation. Rolling or expanding chronological evaluation is required. Overlapping targets require purging and an appropriate gap or embargo so that training information cannot leak into later evaluation labels.

## Evaluation requirements

Predictions must be evaluated net of realistic fees, spread, slippage, latency, and market impact. Model accuracy alone is not a promotion criterion. Statistical significance alone does not prove future profitability. Evaluation must compare simple baselines, include calibration where relevant, report economic outcomes and tail behavior, and test feature, seed, regime, and retraining stability.

Repeated optimization against historical winners produces automated overfitting risk. Candidate, feature, hyperparameter, seed, threshold, and model-family attempts all consume the frozen experiment budget and must be included in multiple-testing governance.

## Historical-result boundary

Alpha Search A outcomes cannot be used as a search oracle. Alpha Search B outcomes cannot be used as a search oracle. A model may not search for parameters that repair those rejected programs, encode their validation or holdout as training feedback, or relabel their mechanisms to evade the future-strategy overlap audit.

## Runtime boundary

FreqAI may be considered only as an isolated future implementation after independent DeltaGrid approval and independent-engine evidence. Freqtrade, FreqAI, or any other runtime cannot authorize production, trading, orders, or capital. Runtime parity is a technical gate, not proof of alpha.

## Promotion boundary

Any future model remains research evidence until every frozen development, validation, sealed-holdout, cost, null, stability, parity, lookahead, recursive, operational, and paper-only gate passes. Passing those gates still does not automatically authorize capital or live trading. Proof-capital and live-trading decisions require separate explicit contracts.

## Fail-closed rule

Leakage, unverifiable feature timing, random authoritative splitting, exhausted search budget, unstable seeds, failed baselines, failed costs, drift, failed parity, or an expired model rejects or disables the model according to the future contract. An ML system cannot change its own gates, refresh its holdout, authorize a rescue, or promote itself.
