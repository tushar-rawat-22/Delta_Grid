from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "docs" / "documentation-status.json"
DOCS_HOME = ROOT / "docs" / "README.md"
BANNER_BODY_BASE_COMMIT = "60b5514adf2d2665c8ab35a3ec2c2e20b635ee87"

SUPERSEDED_PATHS = {
    "docs/CHARTER.md",
    "docs/DELTAGRID_PRODUCT_RESET.md",
    "docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md",
    "docs/DOCUMENTATION_REGISTRY.md",
    "docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md",
    "docs/PROJECT_SOURCE_OF_TRUTH.md",
    "docs/ROADMAP.md",
    "docs/STRATEGY_RESEARCH_ROADMAP.md",
}
HISTORICAL_TOP_LEVEL_PATHS = {
    "docs/ARCHITECTURE_STATE.md",
    "docs/MISSION_INDEX.md",
}
EXPECTED_ADR_PATHS = {
    "docs/ADR/ADR-0001-safe-offchain-monitor.md",
    "docs/ADR/ADR-0002-git-commit-discipline.md",
    "docs/ADR/ADR-0003-local-profit-simulator-risk-engine.md",
    "docs/ADR/ADR-0004-market-data-schema-opportunity-store.md",
    "docs/ADR/ADR-0005-chain-monitor-market-schema-integration.md",
    "docs/ADR/ADR-0006-token-pool-seed-registry.md",
    "docs/ADR/ADR-0007-pool-price-snapshot-simulator.md",
    "docs/ADR/ADR-0008-local-route-builder.md",
    "docs/ADR/ADR-0009-historical-data-backtest-framework.md",
    "docs/ADR/ADR-0010-strategy-regime-analysis.md",
    "docs/ADR/ADR-0011-optimized-opportunity-detector.md",
    "docs/ADR/ADR-0012-closed-loop-route-builder.md",
    "docs/ADR/ADR-0013-real-historical-market-data-ingestion.md",
    "docs/ADR/ADR-0014-strategy-validation-engine.md",
    "docs/ADR/ADR-0015-strategy-candidate-lab.md",
    "docs/ADR/ADR-0016-drawdown-control-lab.md",
    "docs/ADR/ADR-0017-walk-forward-candidate-lab.md",
    "docs/ADR/ADR-0018-strategy-diagnostics.md",
    "docs/ADR/ADR-0019-stability-rework-lab.md",
    "docs/ADR/ADR-0020-regime-kernel-compression-breakout.md",
    "docs/ADR/ADR-0021-volatility-targeted-tsmom.md",
    "docs/ADR/ADR-0022-funding-basis-data-model.md",
    "docs/ADR/ADR-0023-funding-basis-ingestion.md",
    "docs/ADR/ADR-0024-delta-neutral-funding-strategy-lab.md",
    "docs/ADR/ADR-0025-delta-neutral-funding-backtest-engine.md",
    "docs/ADR/ADR-0026-funding-walk-forward-validation.md",
    "docs/ADR/ADR-0027-liquidation-leverage-risk-model.md",
    "docs/ADR/ADR-0028-execution-cost-slippage-simulator.md",
    "docs/ADR/ADR-0029-multi-symbol-funding-scanner.md",
    "docs/ADR/ADR-0030-candidate-ranking-engine.md",
    "docs/ADR/ADR-0031-5-ai-learning-dataset-registry.md",
    "docs/ADR/ADR-0031-paper-trading-engine.md",
    "docs/ADR/ADR-0032-research-dashboard-alerts.md",
    "docs/ADR/ADR-0033-unified-free-shadow-research-runner.md",
    "docs/ADR/ADR-0034-shadow-research-run-history-inspector.md",
    "docs/ADR/ADR-0035-shadow-candidate-replay-harness.md",
    "docs/ADR/ADR-0036-shadow-replay-performance-reporter.md",
    "docs/ADR/ADR-0037-shadow-research-decision-gate.md",
    "docs/ADR/ADR-0038-shadow-paper-observation-ledger.md",
    "docs/ADR/ADR-0039-shadow-observation-lifecycle-manager.md",
    "docs/ADR/ADR-0040-shadow-observation-pnl-attribution-engine.md",
    "docs/ADR/ADR-0041-local-mission-automation-harness.md",
    "docs/ADR/ADR-0042-one-command-mission-pack-runner.md",
    "docs/ADR/ADR-0043-shadow-observation-break-even-tracker.md",
    "docs/ADR/ADR-0044-shadow-observation-close-eligibility-engine.md",
    "docs/ADR/ADR-0045-shadow-observation-outcome-finalizer.md",
    "docs/ADR/ADR-0046-shadow-observation-outcome-analytics-dashboard.md",
    "docs/ADR/ADR-0047-shadow-research-executive-daily-report.md",
    "docs/ADR/ADR-0048-shadow-research-promotion-readiness-gate.md",
    "docs/ADR/ADR-0049-real-market-public-data-ingestion.md",
    "docs/ADR/ADR-0050-historical-public-funding-basis-dataset-builder.md",
    "docs/ADR/ADR-0051-funding-basis-alpha-scanner.md",
    "docs/ADR/ADR-0052-cost-calibration-break-even-sensitivity-engine.md",
    "docs/ADR/ADR-0053-calibrated-shadow-observation-planner.md",
    "docs/ADR/ADR-0054-shadow-plan-to-ledger-bridge.md",
    "docs/ADR/ADR-0055-shadow-ledger-tracking-updater.md",
    "docs/ADR/ADR-0056-shadow-tracking-performance-reporter.md",
    "docs/ADR/ADR-0057-shadow-tracking-alert-invalidation-router.md",
    "docs/ADR/ADR-0058-shadow-research-control-plane.md",
    "docs/ADR/ADR-0059-multi-strategy-research-factory.md",
    "docs/ADR/ADR-0060-data-quality-regime-intelligence-engine.md",
    "docs/ADR/ADR-0061-shadow-portfolio-simulator.md",
    "docs/ADR/ADR-0062-research-promotion-board.md",
    "docs/ADR/ADR-0063-paper-trading-sandbox.md",
    "docs/ADR/ADR-0064-institutional-risk-control-layer.md",
    "docs/ADR/ADR-0065-capital-readiness-review.md",
    "docs/ADR/ADR-0066-paper-observation-performance-monitor.md",
    "docs/ADR/ADR-0067-paper-drawdown-kill-switch.md",
    "docs/ADR/ADR-0068-paper-recovery-stability-monitor.md",
    "docs/ADR/ADR-0069-multi-cycle-paper-observation-tracker.md",
    "docs/ADR/ADR-0070-ai-paper-outcome-learning-engine.md",
    "docs/ADR/ADR-0071-ai-feature-quality-drift-guard.md",
    "docs/ADR/ADR-0072-ai-paper-dataset-expansion-scheduler.md",
    "docs/ADR/ADR-0073-ai-outcome-dataset-builder-pack.md",
    "docs/ADR/ADR-0074-ai-feature-store-training-dataset-registry.md",
    "docs/ADR/ADR-0075-ai-paper-outcome-collection-label-finalizer.md",
    "docs/ADR/ADR-0076-ai-label-quality-leakage-guard.md",
    "docs/ADR/ADR-0078-ai-offline-evaluation-governance-board.md",
    "docs/ADR/ADR-0079-ai-research-recommendation-engine.md",
    "docs/ADR/ADR-0080-autonomous-policy-gate.md",
    "docs/ADR/ADR-0081-autonomous-paper-signal-engine.md",
    "docs/ADR/ADR-0082-paper-execution-agent.md",
    "docs/ADR/ADR-0083-self-learning-feedback-loop.md",
    "docs/ADR/ADR-0084-5-institutional-alpha-research-benchmark-lab.md",
    "docs/ADR/ADR-0084-6-multi-strategy-backtest-pack.md",
    "docs/ADR/ADR-0084-7-walk-forward-robustness-gate.md",
    "docs/ADR/ADR-0084-8-alpha-candidate-promotion-pack.md",
    "docs/ADR/ADR-0084-closure-evidence-correction.md",
    "docs/ADR/ADR-0084-offline-model-training-harness.md",
    "docs/ADR/ADR-0085-funding-carry-research-charter.md",
    "docs/ADR/ADR-0086-real-market-data-foundation.md",
    "docs/ADR/ADR-0087-dataset-certification-quality-gate.md",
    "docs/ADR/ADR-0088-execution-cost-reality-model.md",
    "docs/ADR/ADR-0089-baseline-strategy-falsification.md",
    "docs/ADR/ADR-0090-directional-strategy-tournament.md",
}
DESIGN_ONLY_PATHS = {"docs/DELTA_AUTONOMY_ARCHITECTURE.md"}

TARGET_STATUS = {
    **{path: "SUPERSEDED" for path in SUPERSEDED_PATHS},
    **{path: "HISTORICAL" for path in HISTORICAL_TOP_LEVEL_PATHS},
    **{path: "HISTORICAL" for path in EXPECTED_ADR_PATHS},
    **{path: "DESIGN_ONLY" for path in DESIGN_ONLY_PATHS},
}
TARGET_PATHS = set(TARGET_STATUS)
CHANGED_MARKDOWN_PATHS = TARGET_PATHS | {"docs/README.md"}

STATUS_MARKER = re.compile(
    r"<!-- deltagrid-document-status: "
    r"(HISTORICAL|SUPERSEDED|DESIGN_ONLY) -->"
)
VISIBLE_HEADINGS = {
    "SUPERSEDED": "> **Superseded document**",
    "HISTORICAL_TOP_LEVEL": "> **Historical document**",
    "HISTORICAL_ADR": "> **Historical architecture decision**",
    "DESIGN_ONLY": "> **Design-only document**",
}
EXPECTED_CLASSIFICATION_COUNTS = {
    "CURRENT_PUBLIC": 4,
    "CURRENT_INTERNAL": 4,
    "HISTORICAL": 97,
    "SUPERSEDED": 8,
    "DESIGN_ONLY": 2,
    "EVIDENCE_IMMUTABLE": 10,
    "MACHINE_REFERENCE": 34,
}
FENCE_TOKENS = ("~" * 3, chr(96) * 3)


def repo_path(relative: str) -> Path:
    return ROOT / relative


def read(relative: str) -> str:
    return repo_path(relative).read_text(encoding="utf-8")


def normalized(text: str) -> str:
    semantic_text = re.sub(r"[>`*“”]", "", text)
    return " ".join(semantic_text.casefold().split())


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def registry_by_path() -> dict[str, dict]:
    return {item["path"]: item for item in load_registry()["documents"]}


def expected_heading(path: str) -> str:
    if path in SUPERSEDED_PATHS:
        return VISIBLE_HEADINGS["SUPERSEDED"]
    if path in HISTORICAL_TOP_LEVEL_PATHS:
        return VISIBLE_HEADINGS["HISTORICAL_TOP_LEVEL"]
    if path in EXPECTED_ADR_PATHS:
        return VISIBLE_HEADINGS["HISTORICAL_ADR"]
    return VISIBLE_HEADINGS["DESIGN_ONLY"]


def banner_segment(path: str) -> str:
    lines = read(path).splitlines(keepends=True)
    marker_index = next(
        index
        for index, line in enumerate(lines)
        if STATUS_MARKER.fullmatch(line.strip())
    )
    end = marker_index + 1
    if end < len(lines) and not lines[end].strip():
        end += 1
    while end < len(lines) and lines[end].lstrip().startswith(">"):
        end += 1
    return "".join(lines[marker_index:end])


def markdown_links(text: str) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)


def heading_slugs(path: Path) -> set[str]:
    slugs: set[str] = set()
    occurrences: dict[str, int] = {}
    text = path.read_text(encoding="utf-8")
    for heading in re.findall(
        r"^#{1,6}\s+(.+?)\s*#*\s*$",
        text,
        re.MULTILINE,
    ):
        plain = re.sub(r"[\*_~]", "", heading).casefold()
        base = re.sub(r"[^\w\- ]", "", plain)
        base = re.sub(r"\s+", "-", base.strip())
        if not base:
            continue
        duplicate = occurrences.get(base, 0)
        slugs.add(base if duplicate == 0 else f"{base}-{duplicate}")
        occurrences[base] = duplicate + 1
    return slugs


def assert_relative_link_resolves(source: Path, link: str) -> None:
    target_text, separator, fragment = link.partition("#")
    if "://" in target_text or target_text.startswith(("mailto:", "tel:")):
        return
    decoded_target = unquote(target_text)
    target = source if not decoded_target else source.parent / decoded_target
    assert target.exists(), f"Broken link in {source}: {link}"
    if separator and fragment and target.suffix.casefold() == ".md":
        assert unquote(fragment).casefold() in heading_slugs(target), (
            f"Broken fragment in {source}: {link}"
        )


def banner_is_inside_fence_or_details(path: str, line_index: int) -> bool:
    fence: str | None = None
    details_depth = 0
    for line in read(path).splitlines()[:line_index]:
        stripped = line.lstrip()
        if fence is None:
            fence = next(
                (token for token in FENCE_TOKENS if stripped.startswith(token)),
                None,
            )
        elif stripped.startswith(fence):
            fence = None
        lower = stripped.casefold()
        details_depth += lower.count("<details")
        details_depth -= lower.count("</details>")
    return fence is not None or details_depth > 0


def remove_status_banner(payload: bytes) -> bytes:
    lines = payload.splitlines(keepends=True)
    marker_indexes = [
        index
        for index, line in enumerate(lines)
        if STATUS_MARKER.fullmatch(line.decode("utf-8").strip())
    ]
    assert len(marker_indexes) == 1
    start = marker_indexes[0]
    end = start + 1
    if end < len(lines) and not lines[end].strip():
        end += 1
    quote_start = end
    while end < len(lines) and lines[end].lstrip().startswith(b">"):
        end += 1
    assert end > quote_start
    if end < len(lines) and not lines[end].strip():
        end += 1
    return b"".join(lines[:start] + lines[end:])


def test_exact_banner_target_inventory() -> None:
    actual_adr_paths = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "docs" / "ADR").glob("*.md")
    }
    discovered = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "docs").rglob("*.md")
        if STATUS_MARKER.search(path.read_text(encoding="utf-8"))
    }

    assert SUPERSEDED_PATHS == {
        "docs/CHARTER.md",
        "docs/DELTAGRID_PRODUCT_RESET.md",
        "docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md",
        "docs/DOCUMENTATION_REGISTRY.md",
        "docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md",
        "docs/PROJECT_SOURCE_OF_TRUTH.md",
        "docs/ROADMAP.md",
        "docs/STRATEGY_RESEARCH_ROADMAP.md",
    }
    assert HISTORICAL_TOP_LEVEL_PATHS == {
        "docs/ARCHITECTURE_STATE.md",
        "docs/MISSION_INDEX.md",
    }
    assert DESIGN_ONLY_PATHS == {"docs/DELTA_AUTONOMY_ARCHITECTURE.md"}
    assert actual_adr_paths == EXPECTED_ADR_PATHS
    assert len(EXPECTED_ADR_PATHS) == 95
    assert len(TARGET_PATHS) == 106
    assert discovered == TARGET_PATHS


def test_each_target_has_one_matching_marker() -> None:
    registered = registry_by_path()
    for path, expected_status in TARGET_STATUS.items():
        markers = STATUS_MARKER.findall(read(path))
        assert markers == [expected_status], path
        assert registered[path]["classification"] == expected_status


def test_each_target_has_one_visible_banner_near_top() -> None:
    all_headings = tuple(VISIBLE_HEADINGS.values())
    for path in TARGET_PATHS:
        lines = read(path).splitlines()
        heading = expected_heading(path)
        assert lines.count(heading) == 1, path
        assert sum(lines.count(candidate) for candidate in all_headings) == 1
        non_empty = [line.strip() for line in lines if line.strip()]
        assert non_empty.index(heading) < 12, path
        marker = f"<!-- deltagrid-document-status: {TARGET_STATUS[path]} -->"
        assert non_empty.index(marker) < 12, path


def test_banners_are_outside_code_fences_and_details_blocks() -> None:
    for path in TARGET_PATHS:
        lines = read(path).splitlines()
        marker_index = next(
            index
            for index, line in enumerate(lines)
            if STATUS_MARKER.fullmatch(line.strip())
        )
        heading_index = lines.index(expected_heading(path))
        assert not banner_is_inside_fence_or_details(path, marker_index), path
        assert not banner_is_inside_fence_or_details(path, heading_index), path


def test_banner_links_are_category_correct_and_resolve() -> None:
    for path in TARGET_PATHS:
        segment = banner_segment(path)
        links = markdown_links(segment)
        expected = (
            {"../README.md", "../DELTAGRID_FINAL_FREEZE.md"}
            if path in EXPECTED_ADR_PATHS
            else {"README.md", "DELTAGRID_FINAL_FREEZE.md"}
        )
        assert set(links) == expected, path
        assert len(links) == 2, path
        for link in links:
            assert_relative_link_resolves(repo_path(path), link)


def test_superseded_and_historical_banners_limit_current_authority() -> None:
    for path in SUPERSEDED_PATHS:
        text = normalized(banner_segment(path))
        assert "body is preserved" in text
        assert "no longer controls current work" in text
        assert "active" in text and "current" in text and "next" in text
        assert "original phase" in text
        assert "do not authorize present research or operation" in text

    for path in HISTORICAL_TOP_LEVEL_PATHS:
        text = normalized(banner_segment(path))
        assert "body is preserved" in text
        assert "does not define or authorize current work" in text


def test_adr_banners_limit_historical_accepted_status() -> None:
    for path in EXPECTED_ADR_PATHS:
        text = normalized(banner_segment(path))
        assert "decision accepted for the deltagrid phase" in text
        assert "accepted does not grant current research" in text
        for boundary in (
            "paper trading",
            "live trading",
            "capital",
            "ml",
            "autonomous authority",
        ):
            assert boundary in text, path


def test_design_banner_denies_every_current_authority() -> None:
    text = normalized(banner_segment("docs/DELTA_AUTONOMY_ARCHITECTURE.md"))
    assert "possible future architecture" in text
    assert "not a description of currently authorized operation" in text
    for boundary in (
        "does not authorize ml",
        "paper trading",
        "live trading",
        "capital deployment",
        "autonomous execution",
    ):
        assert boundary in text


def test_protected_documents_have_no_status_banner() -> None:
    protected = {
        ROOT / "docs" / "DELTAGRID_FINAL_FREEZE.md",
        ROOT / "docs" / "DELTAGRID_FINAL_PROJECT_REPORT.md",
        ROOT / "docs" / "DELTAGRID_ML_RESEARCH_ADAPTER.md",
    }
    protected.update((ROOT / "contracts").rglob("*"))
    protected.update((ROOT / "offchain" / "research" / "contracts").rglob("*"))
    protected.update((ROOT / "docs" / "evidence").rglob("*"))
    protected.update((ROOT / "docs").glob("ALPHA_SEARCH*.md"))
    protected.update((ROOT / "docs").glob("MISSION89*.md"))
    protected.update((ROOT / "docs").glob("MISSION90*.md"))
    protected.update((ROOT / "docs").glob("MISSION_91*.md"))
    protected.update((ROOT / "docs").glob("MISSION_92*.md"))

    marker_prefix = b"<!-- deltagrid-document-status:"
    for path in protected:
        if path.is_file():
            assert marker_prefix not in path.read_bytes(), path


def test_all_changed_markdown_links_and_fragments_resolve() -> None:
    for relative in CHANGED_MARKDOWN_PATHS:
        source = repo_path(relative)
        for link in markdown_links(source.read_text(encoding="utf-8")):
            assert_relative_link_resolves(source, link)


def test_registry_inventory_and_classifications_are_unchanged() -> None:
    registry = load_registry()
    items = registry["documents"]
    counts = Counter(item["classification"] for item in items)
    assert len(items) == 159
    assert len({item["path"] for item in items}) == 159
    assert counts == EXPECTED_CLASSIFICATION_COUNTS
    assert registry_by_path()["docs/DELTAGRID_ML_RESEARCH_ADAPTER.md"][
        "classification"
    ] == "DESIGN_ONLY"


def test_registry_records_completed_banner_treatment() -> None:
    registered = registry_by_path()
    for path, expected_status in TARGET_STATUS.items():
        item = registered[path]
        assert item["classification"] == expected_status
        assert item["recommended_treatment"] == "LEAVE_UNCHANGED"
        assert item["conflicts_with_current_state"] is False
        note = normalized(item["notes"])
        assert "batch 3 added" in note
        assert "banner" in note
        assert "body remains preserved" in note


def test_docs_navigation_describes_completed_banner_work() -> None:
    text = normalized(DOCS_HOME.read_text(encoding="utf-8"))
    for statement in (
        "major superseded documents listed below now carry visible status banners",
        "architecture_state.md and mission_index.md are visibly marked historical",
        "all adrs are visibly marked as historical decisions",
        "delta_autonomy_architecture.md is visibly marked design-only",
        "clarify present authority without changing the preserved historical or design bodies",
    ):
        assert statement in text


def test_historical_bodies_and_required_markers_match_banner_base() -> None:
    required_pattern = re.compile(
        rb"(?m)^(?:#{1,6} .+|<!-- MISSION-[A-Z0-9-]+:(?:START|END) -->)$"
    )
    for path in TARGET_PATHS:
        current = repo_path(path).read_bytes()
        base = subprocess.run(
            ["git", "show", f"{BANNER_BODY_BASE_COMMIT}:{path}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        assert remove_status_banner(current) == base, path
        assert set(required_pattern.findall(base)) <= set(
            required_pattern.findall(current)
        ), path
