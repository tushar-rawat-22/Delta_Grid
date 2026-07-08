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

from backtest.candidate_ranking_engine import (
    ensure_schema as ensure_candidate_ranking_schema,
)

from backtest.paper_trading_engine import (
    ensure_schema as ensure_paper_trading_schema,
)


load_dotenv(OFFCHAIN_ROOT / "config" / ".env")

DEFAULT_DB_PATH = os.getenv("DB_PATH", "deltagrid.db")


def safe_decimal(value, default="0"):
    if value is None:
        return Decimal(default)

    return to_decimal(value)


def safe_div(numerator, denominator):
    numerator = safe_decimal(numerator)
    denominator = safe_decimal(denominator)

    if denominator == 0:
        return Decimal("0")

    return numerator / denominator


def ensure_schema(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_learning_examples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_ranking_run_label TEXT NOT NULL,
        source_paper_run_label TEXT NOT NULL,
        candidate_result_id INTEGER NOT NULL,
        paper_position_id INTEGER,
        paper_trade_id INTEGER,
        symbol TEXT NOT NULL,
        annualized_funding_rate_pct TEXT NOT NULL,
        net_expected_edge_pct TEXT NOT NULL,
        edge_to_cost_ratio TEXT NOT NULL,
        liquidity_score TEXT NOT NULL,
        funding_score TEXT NOT NULL,
        basis_risk_penalty TEXT NOT NULL,
        scanner_score TEXT NOT NULL,
        composite_score TEXT NOT NULL,
        combined_cost_pct TEXT NOT NULL,
        scanner_final_verdict TEXT NOT NULL,
        ranking_final_verdict TEXT NOT NULL,
        walk_forward_verdict TEXT NOT NULL,
        liquidation_verdict TEXT NOT NULL,
        execution_cost_verdict TEXT NOT NULL,
        paper_position_verdict TEXT NOT NULL,
        paper_trade_verdict TEXT NOT NULL,
        simulated_net_return_pct TEXT NOT NULL,
        simulated_net_pnl_usd TEXT NOT NULL,
        label_profitable INTEGER NOT NULL,
        label_go INTEGER NOT NULL,
        eligible_for_training INTEGER NOT NULL,
        features_json TEXT NOT NULL,
        labels_json TEXT NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ai_model_registry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_label TEXT NOT NULL,
        source_learning_run_label TEXT NOT NULL,
        model_name TEXT NOT NULL,
        model_version TEXT NOT NULL,
        model_type TEXT NOT NULL,
        training_examples INTEGER NOT NULL,
        eligible_training_examples INTEGER NOT NULL,
        positive_labels INTEGER NOT NULL,
        negative_labels INTEGER NOT NULL,
        feature_names_json TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        model_params_json TEXT NOT NULL,
        approval_status TEXT NOT NULL,
        approved_for_research INTEGER NOT NULL,
        approved_for_paper INTEGER NOT NULL,
        approved_for_live INTEGER NOT NULL,
        final_verdict TEXT NOT NULL,
        recommended_action TEXT NOT NULL,
        assumptions_json TEXT NOT NULL,
        created_at_utc TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def prepare_database(db_path):
    db_path = resolve_db_path(db_path)

    init_market_database(db_path)
    ensure_funding_basis_schema(db_path)
    ensure_candidate_ranking_schema(db_path)
    ensure_paper_trading_schema(db_path)
    ensure_schema(db_path)

    return db_path


def load_candidate_trade_rows(db_path, ranking_run_label, paper_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        c.id,
        c.symbol,
        c.annualized_funding_rate_pct,
        c.net_expected_edge_pct,
        c.edge_to_cost_ratio,
        c.liquidity_score,
        c.funding_score,
        c.basis_risk_penalty,
        c.scanner_score,
        c.composite_score,
        c.combined_cost_pct,
        c.scanner_final_verdict,
        c.final_verdict,
        c.walk_forward_verdict,
        c.liquidation_verdict,
        c.execution_cost_verdict,
        p.id,
        p.final_verdict,
        t.id,
        t.trade_verdict,
        t.simulated_net_return_pct,
        t.simulated_net_pnl_usd
    FROM candidate_ranking_results c
    LEFT JOIN paper_trading_positions p
        ON p.candidate_result_id = c.id
        AND p.run_label = ?
    LEFT JOIN paper_trading_trades t
        ON t.position_id = p.id
        AND t.run_label = ?
    WHERE c.run_label = ?
    ORDER BY CAST(c.composite_score AS REAL) DESC
    """, (
        paper_run_label,
        paper_run_label,
        ranking_run_label,
    )).fetchall()

    conn.close()

    result = []

    for row in rows:
        result.append({
            "candidate_result_id": int(row[0]),
            "symbol": row[1],
            "annualized_funding_rate_pct": safe_decimal(row[2]),
            "net_expected_edge_pct": safe_decimal(row[3]),
            "edge_to_cost_ratio": safe_decimal(row[4]),
            "liquidity_score": safe_decimal(row[5]),
            "funding_score": safe_decimal(row[6]),
            "basis_risk_penalty": safe_decimal(row[7]),
            "scanner_score": safe_decimal(row[8]),
            "composite_score": safe_decimal(row[9]),
            "combined_cost_pct": safe_decimal(row[10]),
            "scanner_final_verdict": row[11] or "UNKNOWN",
            "ranking_final_verdict": row[12] or "UNKNOWN",
            "walk_forward_verdict": row[13] or "UNKNOWN",
            "liquidation_verdict": row[14] or "UNKNOWN",
            "execution_cost_verdict": row[15] or "UNKNOWN",
            "paper_position_id": None if row[16] is None else int(row[16]),
            "paper_position_verdict": row[17] or "NO_PAPER_POSITION",
            "paper_trade_id": None if row[18] is None else int(row[18]),
            "paper_trade_verdict": row[19] or "NO_PAPER_TRADE",
            "simulated_net_return_pct": safe_decimal(row[20]),
            "simulated_net_pnl_usd": safe_decimal(row[21]),
        })

    return result


def build_features(row):
    return {
        "annualized_funding_rate_pct": format(row["annualized_funding_rate_pct"], "f"),
        "net_expected_edge_pct": format(row["net_expected_edge_pct"], "f"),
        "edge_to_cost_ratio": format(row["edge_to_cost_ratio"], "f"),
        "liquidity_score": format(row["liquidity_score"], "f"),
        "funding_score": format(row["funding_score"], "f"),
        "basis_risk_penalty": format(row["basis_risk_penalty"], "f"),
        "scanner_score": format(row["scanner_score"], "f"),
        "composite_score": format(row["composite_score"], "f"),
        "combined_cost_pct": format(row["combined_cost_pct"], "f"),
        "scanner_go": 1 if row["scanner_final_verdict"] == "GO_FOR_RESEARCH" else 0,
        "ranking_go": 1 if row["ranking_final_verdict"] == "GO_FOR_RESEARCH_RANKED" else 0,
        "walk_forward_go": 1 if row["walk_forward_verdict"] == "GO_FOR_RESEARCH" else 0,
        "liquidation_go": 1 if row["liquidation_verdict"] == "LIQUIDATION_LEVERAGE_RISK_ACCEPTABLE_NO_LIVE_TRADING" else 0,
        "execution_cost_go": 1 if row["execution_cost_verdict"] == "EXECUTION_COST_ACCEPTABLE_NO_LIVE_TRADING" else 0,
    }


def build_labels(row, min_label_net_return_pct):
    has_trade = row["paper_trade_id"] is not None
    net_return = row["simulated_net_return_pct"]
    net_pnl = row["simulated_net_pnl_usd"]

    label_profitable = 1 if has_trade and net_return > 0 else 0
    label_go = 1 if has_trade and net_return >= min_label_net_return_pct else 0
    eligible_for_training = 1 if has_trade else 0

    return {
        "has_paper_trade": int(has_trade),
        "label_profitable": label_profitable,
        "label_go": label_go,
        "eligible_for_training": eligible_for_training,
        "simulated_net_return_pct": format(net_return, "f"),
        "simulated_net_pnl_usd": format(net_pnl, "f"),
        "outcome_source": "PAPER_TRADE" if has_trade else "RANKING_OR_PAPER_REJECTION_ONLY",
    }


def learning_example_verdict(labels):
    if labels["eligible_for_training"] == 0:
        return "OBSERVATION_ONLY_NOT_TRAINING_ELIGIBLE"

    if labels["label_go"] == 1:
        return "TRAINING_LABEL_GO"

    return "TRAINING_LABEL_NO_GO"


def learning_example_action(verdict):
    if verdict == "TRAINING_LABEL_GO":
        return "USE_AS_POSITIVE_TRAINING_EXAMPLE"

    if verdict == "TRAINING_LABEL_NO_GO":
        return "USE_AS_NEGATIVE_TRAINING_EXAMPLE"

    return "COLLECT_PAPER_TRADE_OUTCOME_BEFORE_TRAINING"


def insert_learning_example(
    db_path,
    run_label,
    source_ranking_run_label,
    source_paper_run_label,
    row,
    features,
    labels,
    assumptions,
):
    verdict = learning_example_verdict(labels)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO ai_learning_examples (
        run_label,
        source_ranking_run_label,
        source_paper_run_label,
        candidate_result_id,
        paper_position_id,
        paper_trade_id,
        symbol,
        annualized_funding_rate_pct,
        net_expected_edge_pct,
        edge_to_cost_ratio,
        liquidity_score,
        funding_score,
        basis_risk_penalty,
        scanner_score,
        composite_score,
        combined_cost_pct,
        scanner_final_verdict,
        ranking_final_verdict,
        walk_forward_verdict,
        liquidation_verdict,
        execution_cost_verdict,
        paper_position_verdict,
        paper_trade_verdict,
        simulated_net_return_pct,
        simulated_net_pnl_usd,
        label_profitable,
        label_go,
        eligible_for_training,
        features_json,
        labels_json,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_ranking_run_label,
        source_paper_run_label,
        row["candidate_result_id"],
        row["paper_position_id"],
        row["paper_trade_id"],
        row["symbol"],
        format(row["annualized_funding_rate_pct"], "f"),
        format(row["net_expected_edge_pct"], "f"),
        format(row["edge_to_cost_ratio"], "f"),
        format(row["liquidity_score"], "f"),
        format(row["funding_score"], "f"),
        format(row["basis_risk_penalty"], "f"),
        format(row["scanner_score"], "f"),
        format(row["composite_score"], "f"),
        format(row["combined_cost_pct"], "f"),
        row["scanner_final_verdict"],
        row["ranking_final_verdict"],
        row["walk_forward_verdict"],
        row["liquidation_verdict"],
        row["execution_cost_verdict"],
        row["paper_position_verdict"],
        row["paper_trade_verdict"],
        format(row["simulated_net_return_pct"], "f"),
        format(row["simulated_net_pnl_usd"], "f"),
        labels["label_profitable"],
        labels["label_go"],
        labels["eligible_for_training"],
        json.dumps(features),
        json.dumps(labels),
        verdict,
        learning_example_action(verdict),
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def load_training_examples(db_path, learning_run_label):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = cur.execute("""
    SELECT
        id,
        symbol,
        features_json,
        labels_json,
        label_go,
        label_profitable,
        eligible_for_training,
        simulated_net_return_pct
    FROM ai_learning_examples
    WHERE run_label = ?
    ORDER BY id ASC
    """, (
        learning_run_label,
    )).fetchall()

    conn.close()

    examples = []

    for row in rows:
        try:
            features = json.loads(row[2])
        except Exception:
            features = {}

        try:
            labels = json.loads(row[3])
        except Exception:
            labels = {}

        examples.append({
            "id": int(row[0]),
            "symbol": row[1],
            "features": features,
            "labels": labels,
            "label_go": int(row[4]),
            "label_profitable": int(row[5]),
            "eligible_for_training": int(row[6]),
            "simulated_net_return_pct": safe_decimal(row[7]),
        })

    return examples


def average_decimal(values):
    if not values:
        return Decimal("0")

    return sum(values, Decimal("0")) / Decimal(len(values))


def train_baseline_model(
    examples,
    min_training_examples,
    min_positive_examples,
    min_negative_examples,
    min_accuracy,
    min_precision,
):
    eligible = [
        item
        for item in examples
        if item["eligible_for_training"] == 1
    ]

    positives = [
        item
        for item in eligible
        if item["label_go"] == 1
    ]

    negatives = [
        item
        for item in eligible
        if item["label_go"] == 0
    ]

    feature_names = [
        "annualized_funding_rate_pct",
        "net_expected_edge_pct",
        "edge_to_cost_ratio",
        "liquidity_score",
        "funding_score",
        "basis_risk_penalty",
        "scanner_score",
        "composite_score",
        "combined_cost_pct",
        "scanner_go",
        "ranking_go",
        "walk_forward_go",
        "liquidation_go",
        "execution_cost_go",
    ]

    base_metrics = {
        "training_examples": len(examples),
        "eligible_training_examples": len(eligible),
        "positive_labels": len(positives),
        "negative_labels": len(negatives),
    }

    if len(eligible) < min_training_examples:
        return {
            "feature_names": feature_names,
            "metrics": {
                **base_metrics,
                "accuracy": "0",
                "precision": "0",
                "recall": "0",
                "reason": "INSUFFICIENT_TRAINING_EXAMPLES",
            },
            "model_params": {},
            "approval_status": "REJECTED",
            "approved_for_research": 0,
            "approved_for_paper": 0,
            "approved_for_live": 0,
            "final_verdict": "NO_GO_INSUFFICIENT_TRAINING_DATA",
            "recommended_action": "COLLECT_MORE_PAPER_TRADES",
        }

    if len(positives) < min_positive_examples or len(negatives) < min_negative_examples:
        return {
            "feature_names": feature_names,
            "metrics": {
                **base_metrics,
                "accuracy": "0",
                "precision": "0",
                "recall": "0",
                "reason": "INSUFFICIENT_CLASS_BALANCE",
            },
            "model_params": {},
            "approval_status": "REJECTED",
            "approved_for_research": 0,
            "approved_for_paper": 0,
            "approved_for_live": 0,
            "final_verdict": "NO_GO_INSUFFICIENT_CLASS_BALANCE",
            "recommended_action": "COLLECT_POSITIVE_AND_NEGATIVE_EXAMPLES",
        }

    positive_composites = [
        safe_decimal(item["features"].get("composite_score"))
        for item in positives
    ]

    negative_composites = [
        safe_decimal(item["features"].get("composite_score"))
        for item in negatives
    ]

    positive_avg = average_decimal(positive_composites)
    negative_avg = average_decimal(negative_composites)

    threshold = (positive_avg + negative_avg) / Decimal("2")

    tp = 0
    tn = 0
    fp = 0
    fn = 0

    for item in eligible:
        score = safe_decimal(item["features"].get("composite_score"))
        predicted = 1 if score >= threshold else 0
        actual = item["label_go"]

        if predicted == 1 and actual == 1:
            tp += 1
        elif predicted == 0 and actual == 0:
            tn += 1
        elif predicted == 1 and actual == 0:
            fp += 1
        elif predicted == 0 and actual == 1:
            fn += 1

    accuracy = safe_div(tp + tn, len(eligible))
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)

    positive_returns = [
        item["simulated_net_return_pct"]
        for item in positives
    ]

    negative_returns = [
        item["simulated_net_return_pct"]
        for item in negatives
    ]

    approved = accuracy >= min_accuracy and precision >= min_precision

    return {
        "feature_names": feature_names,
        "metrics": {
            **base_metrics,
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "accuracy": format(accuracy, "f"),
            "precision": format(precision, "f"),
            "recall": format(recall, "f"),
            "avg_positive_return_pct": format(average_decimal(positive_returns), "f"),
            "avg_negative_return_pct": format(average_decimal(negative_returns), "f"),
        },
        "model_params": {
            "rule": "predict_label_go_if_composite_score_gte_threshold",
            "composite_score_threshold": format(threshold, "f"),
            "positive_composite_avg": format(positive_avg, "f"),
            "negative_composite_avg": format(negative_avg, "f"),
        },
        "approval_status": "RESEARCH_APPROVED" if approved else "REJECTED",
        "approved_for_research": 1 if approved else 0,
        "approved_for_paper": 0,
        "approved_for_live": 0,
        "final_verdict": "MODEL_REGISTERED_RESEARCH_ONLY" if approved else "NO_GO_MODEL_BELOW_BASELINE",
        "recommended_action": "USE_FOR_RESEARCH_SCORING_ONLY" if approved else "COLLECT_MORE_DATA_OR_REWORK_FEATURES",
    }


def insert_model_registry(
    db_path,
    run_label,
    source_learning_run_label,
    model_name,
    model_version,
    model_type,
    training_result,
    assumptions,
):
    metrics = training_result["metrics"]

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO ai_model_registry (
        run_label,
        source_learning_run_label,
        model_name,
        model_version,
        model_type,
        training_examples,
        eligible_training_examples,
        positive_labels,
        negative_labels,
        feature_names_json,
        metrics_json,
        model_params_json,
        approval_status,
        approved_for_research,
        approved_for_paper,
        approved_for_live,
        final_verdict,
        recommended_action,
        assumptions_json,
        created_at_utc
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_label,
        source_learning_run_label,
        model_name,
        model_version,
        model_type,
        int(metrics.get("training_examples", 0)),
        int(metrics.get("eligible_training_examples", 0)),
        int(metrics.get("positive_labels", 0)),
        int(metrics.get("negative_labels", 0)),
        json.dumps(training_result["feature_names"]),
        json.dumps(training_result["metrics"]),
        json.dumps(training_result["model_params"]),
        training_result["approval_status"],
        training_result["approved_for_research"],
        training_result["approved_for_paper"],
        training_result["approved_for_live"],
        training_result["final_verdict"],
        training_result["recommended_action"],
        json.dumps(assumptions),
        utc_now(),
    ))

    row_id = cur.lastrowid

    conn.commit()
    conn.close()

    return int(row_id)


def run_ai_learning_registry(
    db_path,
    ranking_run_label,
    paper_run_label,
    run_label,
    model_run_label,
    min_label_net_return_pct,
    min_training_examples,
    min_positive_examples,
    min_negative_examples,
    min_accuracy,
    min_precision,
):
    db_path = prepare_database(db_path)

    min_label_net_return_pct = to_decimal(min_label_net_return_pct)
    min_accuracy = to_decimal(min_accuracy)
    min_precision = to_decimal(min_precision)

    assumptions = {
        "research_only": True,
        "ai_learning_only": True,
        "no_private_keys": True,
        "no_signing": True,
        "no_real_trades": True,
        "no_order_execution": True,
        "no_auto_live_retraining": True,
        "ranking_run_label": ranking_run_label,
        "paper_run_label": paper_run_label,
        "run_label": run_label,
        "model_run_label": model_run_label,
        "min_label_net_return_pct": format(min_label_net_return_pct, "f"),
        "min_training_examples": int(min_training_examples),
        "min_positive_examples": int(min_positive_examples),
        "min_negative_examples": int(min_negative_examples),
        "min_accuracy": format(min_accuracy, "f"),
        "min_precision": format(min_precision, "f"),
    }

    rows = load_candidate_trade_rows(
        db_path=db_path,
        ranking_run_label=ranking_run_label,
        paper_run_label=paper_run_label,
    )

    example_ids = []

    for row in rows:
        features = build_features(row)
        labels = build_labels(
            row=row,
            min_label_net_return_pct=min_label_net_return_pct,
        )

        example_id = insert_learning_example(
            db_path=db_path,
            run_label=run_label,
            source_ranking_run_label=ranking_run_label,
            source_paper_run_label=paper_run_label,
            row=row,
            features=features,
            labels=labels,
            assumptions=assumptions,
        )

        example_ids.append(example_id)

    examples = load_training_examples(
        db_path=db_path,
        learning_run_label=run_label,
    )

    training_result = train_baseline_model(
        examples=examples,
        min_training_examples=int(min_training_examples),
        min_positive_examples=int(min_positive_examples),
        min_negative_examples=int(min_negative_examples),
        min_accuracy=min_accuracy,
        min_precision=min_precision,
    )

    model_id = insert_model_registry(
        db_path=db_path,
        run_label=model_run_label,
        source_learning_run_label=run_label,
        model_name="deltagrid_baseline_ai_candidate_scorer",
        model_version=f"{model_run_label}_v1",
        model_type="RULE_BASED_BASELINE_THRESHOLD",
        training_result=training_result,
        assumptions=assumptions,
    )

    metrics = training_result["metrics"]

    return {
        "run_label": run_label,
        "model_run_label": model_run_label,
        "source_ranking_run_label": ranking_run_label,
        "source_paper_run_label": paper_run_label,
        "examples_created": len(example_ids),
        "model_registry_id": model_id,
        "training_examples": metrics.get("training_examples", 0),
        "eligible_training_examples": metrics.get("eligible_training_examples", 0),
        "positive_labels": metrics.get("positive_labels", 0),
        "negative_labels": metrics.get("negative_labels", 0),
        "approval_status": training_result["approval_status"],
        "approved_for_research": bool(training_result["approved_for_research"]),
        "approved_for_paper": bool(training_result["approved_for_paper"]),
        "approved_for_live": bool(training_result["approved_for_live"]),
        "model_metrics": training_result["metrics"],
        "model_params": training_result["model_params"],
        "global_verdict": training_result["final_verdict"],
        "recommended_action": training_result["recommended_action"],
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--ranking-run-label", default="mission_30_candidate_ranking_engine")
    parser.add_argument("--paper-run-label", default="mission_31_paper_trading_engine")
    parser.add_argument("--run-label", default="mission_31_5_ai_learning_dataset")
    parser.add_argument("--model-run-label", default="mission_31_5_ai_model_registry")
    parser.add_argument("--min-label-net-return-pct", default="0.05")
    parser.add_argument("--min-training-examples", type=int, default=100)
    parser.add_argument("--min-positive-examples", type=int, default=20)
    parser.add_argument("--min-negative-examples", type=int, default=20)
    parser.add_argument("--min-accuracy", default="0.55")
    parser.add_argument("--min-precision", default="0.55")

    args = parser.parse_args()

    print("DeltaGrid AI Learning Dataset + Model Registry")
    print("Mode: research-only AI learning")
    print("No private keys. No signing. No real trades.")
    print("AI can score/recommend only. AI cannot execute.")

    result = run_ai_learning_registry(
        db_path=args.db_path,
        ranking_run_label=args.ranking_run_label,
        paper_run_label=args.paper_run_label,
        run_label=args.run_label,
        model_run_label=args.model_run_label,
        min_label_net_return_pct=Decimal(args.min_label_net_return_pct),
        min_training_examples=args.min_training_examples,
        min_positive_examples=args.min_positive_examples,
        min_negative_examples=args.min_negative_examples,
        min_accuracy=Decimal(args.min_accuracy),
        min_precision=Decimal(args.min_precision),
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
