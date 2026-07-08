import sqlite3

from offchain.backtest.shadow_candidate_replay_harness import (
    REPLAY_APPROVED_VERDICT,
    REPLAY_LIVE_TRADING_STATUS,
    resolve_scenarios,
    run_shadow_candidate_replay,
)
from offchain.backtest.research_run_history_inspector import (
    SHADOW_APPROVED_HISTORY_VERDICT,
    inspect_research_run_history,
)


def test_resolve_scenarios_rejects_unknown_name():
    try:
        resolve_scenarios(["does_not_exist"])
    except ValueError as exc:
        assert "Unknown replay scenario" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown replay scenario.")


def test_shadow_candidate_replay_runs_all_scenarios_safely(tmp_path):
    db_path = tmp_path / "mission35.db"

    result = run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission35-test-replay",
        scenario_names=["all"],
    )

    assert result["replay_label"] == "mission35-test-replay"
    assert result["live_trading"] == REPLAY_LIVE_TRADING_STATUS
    assert result["scenario_count"] == 4
    assert result["pipeline_run_count"] == 4
    assert result["total_approved_count"] == 2
    assert result["total_rejected_count"] == 6
    assert result["total_paper_positions_count"] == 2
    assert result["live_trading_breach_count"] == 0
    assert result["global_verdict"] == REPLAY_APPROVED_VERDICT
    assert result["history_summary"]["live_trading_disabled_all"] is True

    scenario_names = {
        item["scenario_name"]
        for item in result["scenario_results"]
    }

    assert scenario_names == {
        "fail_closed_baseline",
        "approved_shadow_btc",
        "mixed_shadow_set",
        "non_universe_rejection",
    }

    with sqlite3.connect(db_path) as conn:
        replay_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_candidate_replay_runs
            WHERE replay_label = ?
            """,
            ("mission35-test-replay",),
        ).fetchone()[0]

        scenario_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM shadow_candidate_replay_scenarios
            WHERE replay_label = ?
            """,
            ("mission35-test-replay",),
        ).fetchone()[0]

    assert replay_count == 1
    assert scenario_count == 4


def test_shadow_candidate_replay_supports_single_scenario_and_history_inspection(tmp_path):
    db_path = tmp_path / "mission35-single.db"

    result = run_shadow_candidate_replay(
        db_path=db_path,
        replay_label="mission35-single-approved",
        scenario_names=["approved_shadow_btc"],
    )

    assert result["scenario_count"] == 1
    assert result["total_approved_count"] == 1
    assert result["total_rejected_count"] == 0
    assert result["total_paper_positions_count"] == 1
    assert result["live_trading_breach_count"] == 0

    history = inspect_research_run_history(db_path=db_path, limit=5)

    assert history["total_runs"] == 1
    assert history["global_verdict"] == SHADOW_APPROVED_HISTORY_VERDICT
    assert history["safety"]["live_trading_disabled_all"] is True
    assert history["safety"]["breach_count"] == 0
