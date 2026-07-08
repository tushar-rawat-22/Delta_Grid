import argparse
import json
import os
import sqlite3
import sys
from decimal import Decimal, getcontext
from pathlib import Path

from dotenv import load_dotenv


getcontext().prec = 40

OFFCHAIN_ROOT = Path(__file__).resolve().parents[1]

if str(OFFCHAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(OFFCHAIN_ROOT))

from db.schema import init_market_database, utc_now

from backtest.funding_basis_model import (
    ensure_schema as ensure_funding_basis_schema,
    resolve_db_path,
    to_decimal,
)

from backtest.multi_symbol_funding_scanner import (
    ensure_schema as ensure_multi_symbol_scan_schema,
)

from backtest.candidate_ranking_engine import (
    ensure_schema as ensure_candidate_ranking_schema,
)

from backtest.paper_trading_engine import (
    ensure_schema as ensure_paper_trading_schema,
)

from backtest.ai_learning_registry import (
    ensure_schema as ensure_ai_learning_schema,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def safe_decimal(value, default="0"):
    if value is None:
        return Decimal(default)

    return to_decimal(value)


def safe_int(value, default=0):
    if value is None:
        return int(default)

    return int(value)


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS research_dashboard_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        scanner_run_label TEXT NOT NULL,
        ranking_run_label TEXT NOT NULL,
        paper_run_label TEXT NOT NULL,
        ai_learning_run_label TEXT NOT NULL,
        ai_model_run_label TEXT NOT NULL,
        scanner_global_verdict TEXT NOT NULL,
        scanner_go_count INTEGER NOT NULL,
        scanner_no_go_count INTEGER NOT NULL,
        best_scanner_symbol TEXT,
        ranking_global_verdict TEXT NOT NULL,
        ranking_go_count INTEGER NOT NULL,
        ranking_no_go_count INTEGER NOT NULL,
        best_ranked_symbol TEXT,
        paper_final_verdict TEXT NOT NULL,
        paper_eligible_candidates INTEGER NOT NULL,
        paper_trades_created INTEGER NOT NULL,
        paper_total_return_pct TEXT NOT NULL,
        paper_max_drawdown_pct TEXT NOT NULL,
        ai_model_final_verdict TEXT NOT NULL,
        ai_model_approval_status TEXT NOT NULL,
        ai_eligible_training_examples INTEGER NOT NULL,
        ai_positive_labels INTEGER NOT NULL,
        ai_negative_labels INTEGER NOT NULL,
        alert_count INTEGER NOT NULL,
        blocking_alert_count INTEGER NOT NULL,
        overall_system_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS research_dashboard_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        alert_level TEXT NOT NULL,
        alert_type TEXT NOT NULL,
        symbol TEXT,
        message TEXT NOT NULL,
        source_component TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        is_blocking INTEGER NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS research_daily_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        report_path TEXT NOT NULL,
        report_markdown TEXT NOT NULL,
        overall_system_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def prepare_database(db_path):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_funding_basis_schema(db_path)
    ensure_multi_symbol_scan_schema(db_path)
    ensure_candidate_ranking_schema(db_path)
    ensure_paper_trading_schema(db_path)
    ensure_ai_learning_schema(db_path)
    ensure_schema(db_path)

    return db_path


def load_scanner_summary(db_path, scanner_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        symbols_requested,
        symbols_scanned,
        results_created,
        go_count,
        no_go_count,
        best_symbol,
        best_scanner_score,
        global_verdict,
        recommended_action
    FROM multi_symbol_funding_scan_summary
    WHERE run_label = ?
    ORDER BY id DESC
    LIMIT 1
    """, (
        scanner_run_label,
    )).fetchone()

    conn.close()

    if row is None:
        return {
            "found": False,
            "symbols_requested": 0,
            "symbols_scanned": 0,
            "results_created": 0,
            "go_count": 0,
            "no_go_count": 0,
            "best_symbol": None,
            "best_scanner_score": Decimal("0"),
            "global_verdict": "MISSING_SCANNER_SUMMARY",
            "recommended_action": "RUN_MULTI_SYMBOL_FUNDING_SCANNER",
        }

    return {
        "found": True,
        "symbols_requested": safe_int(row[0]),
        "symbols_scanned": safe_int(row[1]),
        "results_created": safe_int(row[2]),
        "go_count": safe_int(row[3]),
        "no_go_count": safe_int(row[4]),
        "best_symbol": row[5],
        "best_scanner_score": safe_decimal(row[6]),
        "global_verdict": row[7],
        "recommended_action": row[8],
    }


def load_top_scanner_results(db_path, scanner_run_label, limit=10):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        symbol,
        annualized_funding_rate_pct,
        net_expected_edge_pct,
        edge_to_cost_ratio,
        scanner_score,
        final_verdict,
        recommended_action
    FROM multi_symbol_funding_scan_results
    WHERE run_label = ?
    ORDER BY CAST(scanner_score AS REAL) DESC
    LIMIT ?
    """, (
        scanner_run_label,
        int(limit),
    )).fetchall()

    conn.close()

    return [
        {
            "symbol": row[0],
            "annualized_funding_rate_pct": safe_decimal(row[1]),
            "net_expected_edge_pct": safe_decimal(row[2]),
            "edge_to_cost_ratio": safe_decimal(row[3]),
            "scanner_score": safe_decimal(row[4]),
            "final_verdict": row[5],
            "recommended_action": row[6],
        }
        for row in rows
    ]


def load_ranking_summary(db_path, ranking_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        candidates_seen,
        ranked_count,
        go_count,
        no_go_count,
        best_symbol,
        best_composite_score,
        global_verdict,
        recommended_action
    FROM candidate_ranking_summary
    WHERE run_label = ?
    ORDER BY id DESC
    LIMIT 1
    """, (
        ranking_run_label,
    )).fetchone()

    conn.close()

    if row is None:
        return {
            "found": False,
            "candidates_seen": 0,
            "ranked_count": 0,
            "go_count": 0,
            "no_go_count": 0,
            "best_symbol": None,
            "best_composite_score": Decimal("0"),
            "global_verdict": "MISSING_RANKING_SUMMARY",
            "recommended_action": "RUN_CANDIDATE_RANKING_ENGINE",
        }

    return {
        "found": True,
        "candidates_seen": safe_int(row[0]),
        "ranked_count": safe_int(row[1]),
        "go_count": safe_int(row[2]),
        "no_go_count": safe_int(row[3]),
        "best_symbol": row[4],
        "best_composite_score": safe_decimal(row[5]),
        "global_verdict": row[6],
        "recommended_action": row[7],
    }


def load_top_ranking_results(db_path, ranking_run_label, limit=10):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        symbol,
        scanner_final_verdict,
        annualized_funding_rate_pct,
        net_expected_edge_pct,
        edge_to_cost_ratio,
        composite_score,
        final_verdict,
        recommended_action,
        rejection_reasons_json
    FROM candidate_ranking_results
    WHERE run_label = ?
    ORDER BY CAST(composite_score AS REAL) DESC
    LIMIT ?
    """, (
        ranking_run_label,
        int(limit),
    )).fetchall()

    conn.close()

    results = []

    for row in rows:
        try:
            reasons = json.loads(row[8])
        except Exception:
            reasons = []

        results.append({
            "symbol": row[0],
            "scanner_final_verdict": row[1],
            "annualized_funding_rate_pct": safe_decimal(row[2]),
            "net_expected_edge_pct": safe_decimal(row[3]),
            "edge_to_cost_ratio": safe_decimal(row[4]),
            "composite_score": safe_decimal(row[5]),
            "final_verdict": row[6],
            "recommended_action": row[7],
            "rejection_reasons": reasons,
        })

    return results


def load_paper_summary(db_path, paper_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        candidates_seen,
        eligible_candidates,
        positions_created,
        trades_created,
        starting_equity_usd,
        ending_equity_usd,
        total_pnl_usd,
        total_return_pct,
        max_drawdown_pct,
        win_rate_pct,
        profit_factor,
        final_verdict,
        recommended_action
    FROM paper_trading_summary
    WHERE run_label = ?
    ORDER BY id DESC
    LIMIT 1
    """, (
        paper_run_label,
    )).fetchone()

    conn.close()

    if row is None:
        return {
            "found": False,
            "candidates_seen": 0,
            "eligible_candidates": 0,
            "positions_created": 0,
            "trades_created": 0,
            "starting_equity_usd": Decimal("0"),
            "ending_equity_usd": Decimal("0"),
            "total_pnl_usd": Decimal("0"),
            "total_return_pct": Decimal("0"),
            "max_drawdown_pct": Decimal("0"),
            "win_rate_pct": Decimal("0"),
            "profit_factor": Decimal("0"),
            "final_verdict": "MISSING_PAPER_SUMMARY",
            "recommended_action": "RUN_PAPER_TRADING_ENGINE",
        }

    return {
        "found": True,
        "candidates_seen": safe_int(row[0]),
        "eligible_candidates": safe_int(row[1]),
        "positions_created": safe_int(row[2]),
        "trades_created": safe_int(row[3]),
        "starting_equity_usd": safe_decimal(row[4]),
        "ending_equity_usd": safe_decimal(row[5]),
        "total_pnl_usd": safe_decimal(row[6]),
        "total_return_pct": safe_decimal(row[7]),
        "max_drawdown_pct": safe_decimal(row[8]),
        "win_rate_pct": safe_decimal(row[9]),
        "profit_factor": safe_decimal(row[10]),
        "final_verdict": row[11],
        "recommended_action": row[12],
    }


def load_ai_model_summary(db_path, ai_model_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    row = cur.execute("""
    SELECT
        model_name,
        model_version,
        model_type,
        training_examples,
        eligible_training_examples,
        positive_labels,
        negative_labels,
        approval_status,
        approved_for_research,
        approved_for_paper,
        approved_for_live,
        final_verdict,
        recommended_action
    FROM ai_model_registry
    WHERE run_label = ?
    ORDER BY id DESC
    LIMIT 1
    """, (
        ai_model_run_label,
    )).fetchone()

    conn.close()

    if row is None:
        return {
            "found": False,
            "model_name": None,
            "model_version": None,
            "model_type": None,
            "training_examples": 0,
            "eligible_training_examples": 0,
            "positive_labels": 0,
            "negative_labels": 0,
            "approval_status": "MISSING_AI_MODEL",
            "approved_for_research": 0,
            "approved_for_paper": 0,
            "approved_for_live": 0,
            "final_verdict": "MISSING_AI_MODEL_REGISTRY",
            "recommended_action": "RUN_AI_LEARNING_REGISTRY",
        }

    return {
        "found": True,
        "model_name": row[0],
        "model_version": row[1],
        "model_type": row[2],
        "training_examples": safe_int(row[3]),
        "eligible_training_examples": safe_int(row[4]),
        "positive_labels": safe_int(row[5]),
        "negative_labels": safe_int(row[6]),
        "approval_status": row[7],
        "approved_for_research": safe_int(row[8]),
        "approved_for_paper": safe_int(row[9]),
        "approved_for_live": safe_int(row[10]),
        "final_verdict": row[11],
        "recommended_action": row[12],
    }


def determine_overall_verdict(scanner, ranking, paper, ai_model):
    if not scanner["found"]:
        return "NO_GO_DASHBOARD_MISSING_SCANNER"

    if not ranking["found"]:
        return "NO_GO_DASHBOARD_MISSING_RANKING"

    if not paper["found"]:
        return "NO_GO_DASHBOARD_MISSING_PAPER_TRADING"

    if not ai_model["found"]:
        return "NO_GO_DASHBOARD_MISSING_AI_MODEL"

    if ranking["go_count"] > 0 and paper["final_verdict"] == "GO_PAPER_TRADING_VALIDATED":
        return "RESEARCH_PIPELINE_READY_FOR_MONITORING_NO_LIVE_TRADING"

    return "RESEARCH_PIPELINE_NO_GO_WAIT_FOR_EDGE_NO_LIVE_TRADING"


def dashboard_recommended_action(overall_verdict, scanner, ranking, paper, ai_model):
    if overall_verdict == "RESEARCH_PIPELINE_READY_FOR_MONITORING_NO_LIVE_TRADING":
        return "CONTINUE_PAPER_MONITORING_AND_PREPARE_ALERT_SCHEDULER"

    if scanner["go_count"] == 0:
        return "KEEP_SCANNING_FOR_STRONGER_FUNDING_EDGE"

    if ranking["go_count"] == 0:
        return "WAIT_FOR_RANKED_CANDIDATES"

    if paper["eligible_candidates"] == 0:
        return "WAIT_FOR_ELIGIBLE_PAPER_CANDIDATES"

    if ai_model["eligible_training_examples"] == 0:
        return "COLLECT_MORE_PAPER_TRADE_OUTCOMES"

    return "OBSERVE_ONLY_NO_LIVE_TRADING"


def build_alert(level, alert_type, symbol, message, source_component, action, is_blocking):
    return {
        "alert_level": level,
        "alert_type": alert_type,
        "symbol": symbol,
        "message": message,
        "source_component": source_component,
        "recommended_action": action,
        "is_blocking": 1 if is_blocking else 0,
    }


def generate_alerts(scanner, ranking, paper, ai_model, top_ranking):
    alerts = []

    if not scanner["found"]:
        alerts.append(build_alert(
            "CRITICAL",
            "MISSING_SCANNER_SUMMARY",
            None,
            "No multi-symbol scanner summary found.",
            "scanner",
            "RUN_MULTI_SYMBOL_FUNDING_SCANNER",
            True,
        ))
    elif scanner["go_count"] == 0:
        alerts.append(build_alert(
            "WARNING",
            "NO_SCANNER_GO_CANDIDATES",
            scanner["best_symbol"],
            "Scanner found no GO candidates.",
            "scanner",
            scanner["recommended_action"],
            False,
        ))

    if not ranking["found"]:
        alerts.append(build_alert(
            "CRITICAL",
            "MISSING_RANKING_SUMMARY",
            None,
            "No candidate ranking summary found.",
            "ranking",
            "RUN_CANDIDATE_RANKING_ENGINE",
            True,
        ))
    elif ranking["go_count"] == 0:
        alerts.append(build_alert(
            "WARNING",
            "NO_RANKED_GO_CANDIDATES",
            ranking["best_symbol"],
            "Ranking engine found no GO candidates.",
            "ranking",
            ranking["recommended_action"],
            False,
        ))

    if paper["final_verdict"] != "GO_PAPER_TRADING_VALIDATED":
        alerts.append(build_alert(
            "WARNING",
            "PAPER_TRADING_NOT_VALIDATED",
            None,
            f"Paper trading verdict is {paper['final_verdict']}.",
            "paper_trading",
            paper["recommended_action"],
            False,
        ))

    if paper["eligible_candidates"] == 0:
        alerts.append(build_alert(
            "INFO",
            "NO_ELIGIBLE_PAPER_CANDIDATES",
            None,
            "No candidates qualified for paper trading.",
            "paper_trading",
            "WAIT_FOR_RANKED_CANDIDATES",
            False,
        ))

    if ai_model["approval_status"] != "RESEARCH_APPROVED":
        alerts.append(build_alert(
            "INFO",
            "AI_MODEL_NOT_APPROVED",
            None,
            f"AI model approval status is {ai_model['approval_status']}.",
            "ai_learning",
            ai_model["recommended_action"],
            False,
        ))

    for candidate in top_ranking[:5]:
        if candidate["final_verdict"] != "GO_FOR_RESEARCH_RANKED":
            reason_text = ", ".join(candidate["rejection_reasons"][:3])
            alerts.append(build_alert(
                "INFO",
                "TOP_CANDIDATE_REJECTED",
                candidate["symbol"],
                f"Top ranked candidate rejected: {reason_text}",
                "ranking",
                candidate["recommended_action"],
                False,
            ))

    alerts.append(build_alert(
        "CRITICAL",
        "LIVE_TRADING_DISABLED",
        None,
        "Live trading remains disabled. No private keys, signing, or real trades are permitted.",
        "safety",
        "KEEP_RESEARCH_ONLY",
        True,
    ))

    return alerts


def decimal_to_text(value):
    if isinstance(value, Decimal):
        return format(value, "f")

    return value


def clean_for_json(item):
    if isinstance(item, dict):
        return {
            key: clean_for_json(value)
            for key, value in item.items()
        }

    if isinstance(item, list):
        return [
            clean_for_json(value)
            for value in item
        ]

    if isinstance(item, Decimal):
        return format(item, "f")

    return item


def build_snapshot(
    scanner,
    ranking,
    paper,
    ai_model,
    alerts,
    overall_verdict,
    action,
):
    blocking_alert_count = len([
        alert
        for alert in alerts
        if alert["is_blocking"] == 1
    ])

    metrics = {
        "scanner": clean_for_json(scanner),
        "ranking": clean_for_json(ranking),
        "paper_trading": clean_for_json(paper),
        "ai_model": clean_for_json(ai_model),
        "alert_count": len(alerts),
        "blocking_alert_count": blocking_alert_count,
    }

    return {
        "scanner_global_verdict": scanner["global_verdict"],
        "scanner_go_count": scanner["go_count"],
        "scanner_no_go_count": scanner["no_go_count"],
        "best_scanner_symbol": scanner["best_symbol"],
        "ranking_global_verdict": ranking["global_verdict"],
        "ranking_go_count": ranking["go_count"],
        "ranking_no_go_count": ranking["no_go_count"],
        "best_ranked_symbol": ranking["best_symbol"],
        "paper_final_verdict": paper["final_verdict"],
        "paper_eligible_candidates": paper["eligible_candidates"],
        "paper_trades_created": paper["trades_created"],
        "paper_total_return_pct": paper["total_return_pct"],
        "paper_max_drawdown_pct": paper["max_drawdown_pct"],
        "ai_model_final_verdict": ai_model["final_verdict"],
        "ai_model_approval_status": ai_model["approval_status"],
        "ai_eligible_training_examples": ai_model["eligible_training_examples"],
        "ai_positive_labels": ai_model["positive_labels"],
        "ai_negative_labels": ai_model["negative_labels"],
        "alert_count": len(alerts),
        "blocking_alert_count": blocking_alert_count,
        "overall_system_verdict": overall_verdict,
        "recommended_action": action,
        "metrics_json": json.dumps(metrics),
    }


def render_report_markdown(
    run_label,
    scanner_run_label,
    ranking_run_label,
    paper_run_label,
    ai_learning_run_label,
    ai_model_run_label,
    snapshot,
    scanner,
    ranking,
    paper,
    ai_model,
    top_scanner,
    top_ranking,
    alerts,
):
    lines = []

    lines.append("# DeltaGrid Research Dashboard Report")
    lines.append("")
    lines.append(f"Generated UTC: {utc_now()}")
    lines.append(f"Run label: `{run_label}`")
    lines.append("")
    lines.append("## Overall Verdict")
    lines.append("")
    lines.append(f"- Verdict: `{snapshot['overall_system_verdict']}`")
    lines.append(f"- Recommended action: `{snapshot['recommended_action']}`")
    lines.append(f"- Alert count: `{snapshot['alert_count']}`")
    lines.append(f"- Blocking alert count: `{snapshot['blocking_alert_count']}`")
    lines.append("")
    lines.append("## Source Runs")
    lines.append("")
    lines.append(f"- Scanner: `{scanner_run_label}`")
    lines.append(f"- Ranking: `{ranking_run_label}`")
    lines.append(f"- Paper trading: `{paper_run_label}`")
    lines.append(f"- AI learning: `{ai_learning_run_label}`")
    lines.append(f"- AI model: `{ai_model_run_label}`")
    lines.append("")
    lines.append("## Scanner Summary")
    lines.append("")
    lines.append(f"- Global verdict: `{scanner['global_verdict']}`")
    lines.append(f"- GO count: `{scanner['go_count']}`")
    lines.append(f"- NO-GO count: `{scanner['no_go_count']}`")
    lines.append(f"- Best symbol: `{scanner['best_symbol']}`")
    lines.append("")
    lines.append("## Ranking Summary")
    lines.append("")
    lines.append(f"- Global verdict: `{ranking['global_verdict']}`")
    lines.append(f"- GO count: `{ranking['go_count']}`")
    lines.append(f"- NO-GO count: `{ranking['no_go_count']}`")
    lines.append(f"- Best symbol: `{ranking['best_symbol']}`")
    lines.append("")
    lines.append("## Paper Trading Summary")
    lines.append("")
    lines.append(f"- Final verdict: `{paper['final_verdict']}`")
    lines.append(f"- Eligible candidates: `{paper['eligible_candidates']}`")
    lines.append(f"- Trades created: `{paper['trades_created']}`")
    lines.append(f"- Total return pct: `{decimal_to_text(paper['total_return_pct'])}`")
    lines.append(f"- Max drawdown pct: `{decimal_to_text(paper['max_drawdown_pct'])}`")
    lines.append("")
    lines.append("## AI Learning Summary")
    lines.append("")
    lines.append(f"- Model verdict: `{ai_model['final_verdict']}`")
    lines.append(f"- Approval status: `{ai_model['approval_status']}`")
    lines.append(f"- Eligible training examples: `{ai_model['eligible_training_examples']}`")
    lines.append(f"- Positive labels: `{ai_model['positive_labels']}`")
    lines.append(f"- Negative labels: `{ai_model['negative_labels']}`")
    lines.append(f"- Approved for live: `{ai_model['approved_for_live']}`")
    lines.append("")
    lines.append("## Top Scanner Candidates")
    lines.append("")

    if not top_scanner:
        lines.append("- No scanner candidates found.")
    else:
        for item in top_scanner:
            lines.append(
                f"- `{item['symbol']}` score `{decimal_to_text(item['scanner_score'])}` "
                f"net edge `{decimal_to_text(item['net_expected_edge_pct'])}` "
                f"verdict `{item['final_verdict']}`"
            )

    lines.append("")
    lines.append("## Top Ranked Candidates")
    lines.append("")

    if not top_ranking:
        lines.append("- No ranked candidates found.")
    else:
        for item in top_ranking:
            reasons = ", ".join(item["rejection_reasons"][:3])
            lines.append(
                f"- `{item['symbol']}` composite `{decimal_to_text(item['composite_score'])}` "
                f"verdict `{item['final_verdict']}` reasons `{reasons}`"
            )

    lines.append("")
    lines.append("## Alerts")
    lines.append("")

    for alert in alerts:
        lines.append(
            f"- `{alert['alert_level']}` `{alert['alert_type']}` "
            f"component `{alert['source_component']}` "
            f"blocking `{alert['is_blocking']}`: {alert['message']}"
        )

    lines.append("")
    lines.append("## Safety")
    lines.append("")
    lines.append("- No live trading.")
    lines.append("- No private keys.")
    lines.append("- No signing.")
    lines.append("- No real capital.")
    lines.append("- No autonomous execution.")

    return "\n".join(lines) + "\n"


def write_report(report_path, report_markdown):
    path = Path(report_path).expanduser()

    if not path.is_absolute():
        path = OFFCHAIN_ROOT / path

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_markdown)

    return str(path)


def insert_snapshot(
    db_path,
    run_label,
    scanner_run_label,
    ranking_run_label,
    paper_run_label,
    ai_learning_run_label,
    ai_model_run_label,
    snapshot,
):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO research_dashboard_snapshots (
        run_label,
        scanner_run_label,
        ranking_run_label,
        paper_run_label,
        ai_learning_run_label,
        ai_model_run_label,
        scanner_global_verdict,
        scanner_go_count,
        scanner_no_go_count,
        best_scanner_symbol,
        ranking_global_verdict,
        ranking_go_count,
        ranking_no_go_count,
        best_ranked_symbol,
        paper_final_verdict,
        paper_eligible_candidates,
        paper_trades_created,
        paper_total_return_pct,
        paper_max_drawdown_pct,
        ai_model_final_verdict,
        ai_model_approval_status,
        ai_eligible_training_examples,
        ai_positive_labels,
        ai_negative_labels,
        alert_count,
        blocking_alert_count,
        overall_system_verdict,
        recommended_action,
        metrics_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        scanner_run_label,
        ranking_run_label,
        paper_run_label,
        ai_learning_run_label,
        ai_model_run_label,
        snapshot["scanner_global_verdict"],
        snapshot["scanner_go_count"],
        snapshot["scanner_no_go_count"],
        snapshot["best_scanner_symbol"],
        snapshot["ranking_global_verdict"],
        snapshot["ranking_go_count"],
        snapshot["ranking_no_go_count"],
        snapshot["best_ranked_symbol"],
        snapshot["paper_final_verdict"],
        snapshot["paper_eligible_candidates"],
        snapshot["paper_trades_created"],
        format(snapshot["paper_total_return_pct"], "f"),
        format(snapshot["paper_max_drawdown_pct"], "f"),
        snapshot["ai_model_final_verdict"],
        snapshot["ai_model_approval_status"],
        snapshot["ai_eligible_training_examples"],
        snapshot["ai_positive_labels"],
        snapshot["ai_negative_labels"],
        snapshot["alert_count"],
        snapshot["blocking_alert_count"],
        snapshot["overall_system_verdict"],
        snapshot["recommended_action"],
        snapshot["metrics_json"],
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def insert_alerts(db_path, run_label, alerts):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    alert_ids = []

    for alert in alerts:
        cur.execute("""
        INSERT INTO research_dashboard_alerts (
            run_label,
            alert_level,
            alert_type,
            symbol,
            message,
            source_component,
            recommended_action,
            is_blocking,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_label,
            alert["alert_level"],
            alert["alert_type"],
            alert["symbol"],
            alert["message"],
            alert["source_component"],
            alert["recommended_action"],
            alert["is_blocking"],
            utc_now(),
        ))

        alert_ids.append(int(cur.lastrowid))

    conn.commit()
    conn.close()

    return alert_ids


def insert_report(db_path, run_label, report_path, report_markdown, snapshot):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO research_daily_reports (
        run_label,
        report_path,
        report_markdown,
        overall_system_verdict,
        recommended_action,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        report_path,
        report_markdown,
        snapshot["overall_system_verdict"],
        snapshot["recommended_action"],
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def run_research_dashboard_alerts(
    db_path,
    run_label,
    scanner_run_label,
    ranking_run_label,
    paper_run_label,
    ai_learning_run_label,
    ai_model_run_label,
    report_path,
):
    db_path = prepare_database(db_path)

    scanner = load_scanner_summary(
        db_path=db_path,
        scanner_run_label=scanner_run_label,
    )

    ranking = load_ranking_summary(
        db_path=db_path,
        ranking_run_label=ranking_run_label,
    )

    paper = load_paper_summary(
        db_path=db_path,
        paper_run_label=paper_run_label,
    )

    ai_model = load_ai_model_summary(
        db_path=db_path,
        ai_model_run_label=ai_model_run_label,
    )

    top_scanner = load_top_scanner_results(
        db_path=db_path,
        scanner_run_label=scanner_run_label,
        limit=10,
    )

    top_ranking = load_top_ranking_results(
        db_path=db_path,
        ranking_run_label=ranking_run_label,
        limit=10,
    )

    alerts = generate_alerts(
        scanner=scanner,
        ranking=ranking,
        paper=paper,
        ai_model=ai_model,
        top_ranking=top_ranking,
    )

    overall_verdict = determine_overall_verdict(
        scanner=scanner,
        ranking=ranking,
        paper=paper,
        ai_model=ai_model,
    )

    action = dashboard_recommended_action(
        overall_verdict=overall_verdict,
        scanner=scanner,
        ranking=ranking,
        paper=paper,
        ai_model=ai_model,
    )

    snapshot = build_snapshot(
        scanner=scanner,
        ranking=ranking,
        paper=paper,
        ai_model=ai_model,
        alerts=alerts,
        overall_verdict=overall_verdict,
        action=action,
    )

    snapshot_id = insert_snapshot(
        db_path=db_path,
        run_label=run_label,
        scanner_run_label=scanner_run_label,
        ranking_run_label=ranking_run_label,
        paper_run_label=paper_run_label,
        ai_learning_run_label=ai_learning_run_label,
        ai_model_run_label=ai_model_run_label,
        snapshot=snapshot,
    )

    alert_ids = insert_alerts(
        db_path=db_path,
        run_label=run_label,
        alerts=alerts,
    )

    report_markdown = render_report_markdown(
        run_label=run_label,
        scanner_run_label=scanner_run_label,
        ranking_run_label=ranking_run_label,
        paper_run_label=paper_run_label,
        ai_learning_run_label=ai_learning_run_label,
        ai_model_run_label=ai_model_run_label,
        snapshot=snapshot,
        scanner=scanner,
        ranking=ranking,
        paper=paper,
        ai_model=ai_model,
        top_scanner=top_scanner,
        top_ranking=top_ranking,
        alerts=alerts,
    )

    written_report_path = write_report(
        report_path=report_path,
        report_markdown=report_markdown,
    )

    report_id = insert_report(
        db_path=db_path,
        run_label=run_label,
        report_path=written_report_path,
        report_markdown=report_markdown,
        snapshot=snapshot,
    )

    return {
        "run_label": run_label,
        "snapshot_id": snapshot_id,
        "alert_ids": alert_ids,
        "report_id": report_id,
        "report_path": written_report_path,
        "scanner": clean_for_json(scanner),
        "ranking": clean_for_json(ranking),
        "paper_trading": clean_for_json(paper),
        "ai_model": clean_for_json(ai_model),
        "alert_count": len(alerts),
        "blocking_alert_count": snapshot["blocking_alert_count"],
        "overall_system_verdict": snapshot["overall_system_verdict"],
        "recommended_action": snapshot["recommended_action"],
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--run-label", default="mission_32_research_dashboard_alerts")
    parser.add_argument("--scanner-run-label", default="mission_29_multi_symbol_funding_scanner")
    parser.add_argument("--ranking-run-label", default="mission_30_candidate_ranking_engine")
    parser.add_argument("--paper-run-label", default="mission_31_paper_trading_engine")
    parser.add_argument("--ai-learning-run-label", default="mission_31_5_ai_learning_dataset")
    parser.add_argument("--ai-model-run-label", default="mission_31_5_ai_model_registry")
    parser.add_argument("--report-path", default="/tmp/deltagrid_mission_32_research_dashboard_report.md")

    args = parser.parse_args()

    print("DeltaGrid Research Dashboard + Alerts")
    print("Mode: research dashboard only")
    print("No private keys. No signing. No real trades.")

    result = run_research_dashboard_alerts(
        db_path=args.db_path,
        run_label=args.run_label,
        scanner_run_label=args.scanner_run_label,
        ranking_run_label=args.ranking_run_label,
        paper_run_label=args.paper_run_label,
        ai_learning_run_label=args.ai_learning_run_label,
        ai_model_run_label=args.ai_model_run_label,
        report_path=args.report_path,
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
