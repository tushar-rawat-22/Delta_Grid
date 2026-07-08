# ADR-0032: Research Dashboard + Alerts

## Status

Accepted

## Date

2026-07-08

---

## Context

Mission 31.5 added AI learning dataset and model registry.

DeltaGrid now needs a dashboard/report layer to summarize scanner, ranking, paper-trading, and AI-learning status in one place.

This mission does not add live trading.

---

## Decision

Add research dashboard and alerts.

Files:

- offchain/backtest/research_dashboard_alerts.py
- offchain/tests/test_research_dashboard_alerts.py

Code commit:

- fe0d65a Add research dashboard alerts

---

## Tables Added

- research_dashboard_snapshots
- research_dashboard_alerts
- research_daily_reports

---

## Dashboard Logic

The dashboard summarizes:

- multi-symbol scanner status
- candidate ranking status
- paper-trading status
- AI model registry status
- top scanner candidates
- top ranked candidates
- rejection reasons
- alerts
- blocking safety alerts
- daily markdown research report

---

## Mission 32 Verification

Run label:

- mission_32_research_dashboard_alerts

Latest run summary:

- snapshot=(0, 0, 0, 0, 0, 'REJECTED', 11, 1, 'RESEARCH_PIPELINE_NO_GO_WAIT_FOR_EDGE_NO_LIVE_TRADING', 'KEEP_SCANNING_FOR_STRONGER_FUNDING_EDGE') alerts=[('WARNING', 'NO_SCANNER_GO_CANDIDATES', 'ETHUSDT', 'scanner', 0, 'KEEP_SCANNING_AND_WAIT_FOR_EDGE'), ('WARNING', 'NO_RANKED_GO_CANDIDATES', 'ETHUSDT', 'ranking', 0, 'KEEP_SCANNING_AND_WAIT_FOR_STRONGER_EDGE'), ('WARNING', 'PAPER_TRADING_NOT_VALIDATED', None, 'paper_trading', 0, 'KEEP_SCANNING_AND_WAIT_FOR_RANKED_CANDIDATES'), ('INFO', 'NO_ELIGIBLE_PAPER_CANDIDATES', None, 'paper_trading', 0, 'WAIT_FOR_RANKED_CANDIDATES'), ('INFO', 'AI_MODEL_NOT_APPROVED', None, 'ai_learning', 0, 'COLLECT_MORE_PAPER_TRADES'), ('INFO', 'TOP_CANDIDATE_REJECTED', 'ETHUSDT', 'ranking', 0, 'WAIT_FOR_SCANNER_GO_SIGNAL'), ('INFO', 'TOP_CANDIDATE_REJECTED', 'BTCUSDT', 'ranking', 0, 'WAIT_FOR_SCANNER_GO_SIGNAL'), ('INFO', 'TOP_CANDIDATE_REJECTED', 'SOLUSDT', 'ranking', 0, 'WAIT_FOR_SCANNER_GO_SIGNAL'), ('INFO', 'TOP_CANDIDATE_REJECTED', 'XRPUSDT', 'ranking', 0, 'WAIT_FOR_SCANNER_GO_SIGNAL'), ('INFO', 'TOP_CANDIDATE_REJECTED', 'LTCUSDT', 'ranking', 0, 'WAIT_FOR_SCANNER_GO_SIGNAL')] report=('/tmp/deltagrid_mission_32_research_dashboard_report.md', 'RESEARCH_PIPELINE_NO_GO_WAIT_FOR_EDGE_NO_LIVE_TRADING', 'KEEP_SCANNING_FOR_STRONGER_FUNDING_EDGE')

---

## Investment Committee Verdict

Research dashboard + alerts:

- GO

Current pipeline status:

- depends on scanner, ranking, paper, and AI model outputs

Live trading:

- NO-GO

Reason:

- dashboard is reporting-only
- alerts are research-only
- no exchange gateway
- no private keys
- no signing
- no real trades

---

## Safety

Still forbidden:

- no autonomous live trading
- no private keys
- no signing
- no real capital
- no mainnet execution
- no risk override
