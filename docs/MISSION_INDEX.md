# DeltaGrid Mission Index

## Mission 58

Name: Shadow Research Control Plane and Documentation Registry

Purpose:

- orchestrate the shadow research cycle
- run tracking, performance, and alert routing from one control plane
- verify documentation consistency
- preserve shadow-only safety

## Latest Valid Mission Before Mission 58

Mission 57 routed BTCUSDT and ETHUSDT to continue shadow tracking.

## Current Safety State

- live trading: blocked
- capital deployment: blocked
- private keys: forbidden
- exchange orders: forbidden

## Mission 59

Name: Multi-Strategy Research Factory

Status: Code verified, documented, shadow-only.

Purpose:

- create a strategy registry
- evaluate multiple strategy families
- score strategy candidates
- produce promotion shortlist, watchlist, rejection, and data-insufficient labels
- preserve shadow-only safety

Tables:

- multi_strategy_research_registry
- multi_strategy_research_candidates
- multi_strategy_research_factory_reports

---

## Mission 60

Name: Data Quality and Regime Intelligence Engine

Purpose:

- score public data quality
- classify funding, basis, volatility, and liquidity regimes
- classify market risk state
- gate Mission 59 strategy candidates by regime
- preserve shadow-only safety

Tables:

- data_quality_regime_symbol_reports
- data_quality_strategy_candidate_gates
- data_quality_regime_intelligence_reports

---

## Mission 61

Name: Shadow Portfolio Simulator

Purpose:

- allocate shadow notional across eligible candidates
- apply symbol, strategy, and candidate caps
- estimate concentration risk
- estimate shadow drawdown
- produce portfolio-level verdict
- preserve shadow-only safety

Tables:

- shadow_portfolio_simulations
- shadow_portfolio_allocations
- shadow_portfolio_risk_reports

## Mission 62

Name: Research Promotion Board

Purpose:

- review portfolio-level evidence
- approve, watchlist, block, or reject shadow portfolio promotion
- create board evidence records
- create board decision records
- define next mission scope
- preserve shadow-only safety

Tables:

- research_promotion_board_reviews
- research_promotion_board_evidence_items
- research_promotion_board_decision_records

---

## Mission 63

Name: Paper Trading Sandbox

Purpose:

- convert board-approved shadow allocations into paper-only orders
- simulate fills and positions
- record simulated fees and slippage
- create a paper sandbox session report
- preserve strict no-live-trading safety

Tables:

- paper_sandbox_sessions
- paper_sandbox_orders
- paper_sandbox_fills
- paper_sandbox_positions
- paper_sandbox_reports

---

## Mission 64

Name: Institutional Risk Control Layer

Purpose:

- review paper sandbox sessions
- enforce exposure and cost limits
- verify order/fill integrity
- verify safety invariants
- produce institutional risk decision records
- preserve no-live-trading safety

Tables:

- institutional_risk_control_reviews
- institutional_risk_limit_checks
- institutional_risk_decision_records
