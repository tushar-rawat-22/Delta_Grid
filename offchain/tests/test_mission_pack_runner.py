import json
import subprocess
import sys

import pytest

from scripts.mission_pack_runner import (
    PACK_RUNNER_DRY_RUN,
    PACK_RUNNER_FAIL,
    PACK_RUNNER_PASS,
    apply_file_action,
    is_safe_relative_path,
    render_template,
    run_mission_pack,
    scan_content_forbidden_patterns,
    validate_pack,
)


def write_pack(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_safe_relative_path_rejects_dangerous_paths():
    assert is_safe_relative_path("scripts/example.py") is True
    assert is_safe_relative_path("docs/ADR/example.md") is True

    assert is_safe_relative_path("../escape.py") is False
    assert is_safe_relative_path("/tmp/escape.py") is False
    assert is_safe_relative_path(".env") is False
    assert is_safe_relative_path(".ssh/key") is False
    assert is_safe_relative_path(".git/config") is False


def test_forbidden_content_scanner_detects_unsafe_patterns():
    forbidden = scan_content_forbidden_patterns("PRIVATE_KEY=abc\nsend_order('BTC')")

    assert "PRIVATE_KEY=" in forbidden
    assert "send_order(" in forbidden


def test_validate_pack_rejects_forbidden_content():
    pack = {
        "mission": "bad-pack",
        "code_files": [
            {
                "path": "scripts/bad.py",
                "mode": "overwrite",
                "content": "PRIVATE_KEY=abc",
            }
        ],
    }

    with pytest.raises(ValueError):
        validate_pack(pack)


def test_render_template_replaces_context_values():
    text = render_template(
        "mission={mission}; commit={code_commit}",
        {"mission": "mission42", "code_commit": "abc123 Add thing"},
    )

    assert text == "mission=mission42; commit=abc123 Add thing"


def test_apply_file_action_overwrite_and_append_once(tmp_path):
    root = tmp_path

    overwrite = {
        "path": "docs/example.md",
        "mode": "overwrite",
        "content": "hello {mission}\n",
    }

    result = apply_file_action(
        repo_root=root,
        action=overwrite,
        context={"mission": "mission42"},
    )

    assert result.changed is True
    assert (root / "docs/example.md").read_text(encoding="utf-8") == "hello mission42\n"

    append = {
        "path": "docs/example.md",
        "mode": "append_once",
        "marker": "## Marker",
        "content": "## Marker\ncontent\n",
    }

    first = apply_file_action(root, append, context={})
    second = apply_file_action(root, append, context={})

    assert first.changed is True
    assert second.changed is False
    assert (root / "docs/example.md").read_text(encoding="utf-8").count("## Marker") == 1


def test_run_mission_pack_dry_run_does_not_write_files(tmp_path):
    pack_path = tmp_path / "pack.json"

    write_pack(
        pack_path,
        {
            "mission": "mission42-dry-run-test",
            "code_files": [
                {
                    "path": "scripts/generated.py",
                    "mode": "overwrite",
                    "content": "print('generated')\n",
                }
            ],
            "verification": {
                "skip_full_suite": True,
            },
        },
    )

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    result = run_mission_pack(
        pack_path=pack_path,
        repo_root=tmp_path,
        dry_run=True,
        require_clean_start=True,
    )

    assert result["global_verdict"] == PACK_RUNNER_DRY_RUN
    assert result["dry_run"] is True
    assert not (tmp_path / "scripts/generated.py").exists()


def test_run_mission_pack_applies_and_verifies_without_commit(tmp_path):
    pack_path = tmp_path / "pack.json"

    write_pack(
        pack_path,
        {
            "mission": "mission42-apply-test",
            "code_files": [
                {
                    "path": "scripts/generated_module.py",
                    "mode": "overwrite",
                    "content": "def value():\n    return 42\n",
                },
                {
                    "path": "offchain/tests/test_generated_module.py",
                    "mode": "overwrite",
                    "content": "from scripts.generated_module import value\n\n\ndef test_value():\n    assert value() == 42\n",
                },
            ],
            "verification": {
                "module_file": "scripts/generated_module.py",
                "test_file": "offchain/tests/test_generated_module.py",
                "mission_test": "offchain/tests/test_generated_module.py",
                "skip_full_suite": True,
                "mission_command": f"{sys.executable} -c \"from scripts.generated_module import value; print(value())\"",
            },
        },
    )

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    result = run_mission_pack(
        pack_path=pack_path,
        repo_root=tmp_path,
        dry_run=False,
        commit=False,
        require_clean_start=True,
    )

    assert result["global_verdict"] == PACK_RUNNER_PASS
    assert result["verification"]["failed_count"] == 0
    assert (tmp_path / "scripts/generated_module.py").exists()
    assert (tmp_path / "offchain/tests/test_generated_module.py").exists()


def test_run_mission_pack_fails_on_verification_error(tmp_path):
    pack_path = tmp_path / "pack.json"

    write_pack(
        pack_path,
        {
            "mission": "mission42-fail-test",
            "code_files": [
                {
                    "path": "scripts/bad_module.py",
                    "mode": "overwrite",
                    "content": "def broken(:\n    pass\n",
                }
            ],
            "verification": {
                "module_file": "scripts/bad_module.py",
                "skip_full_suite": True,
            },
        },
    )

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    result = run_mission_pack(
        pack_path=pack_path,
        repo_root=tmp_path,
        dry_run=False,
        commit=False,
        require_clean_start=True,
    )

    assert result["global_verdict"] == PACK_RUNNER_FAIL
    assert result["failed_stage"] == "verification"
    assert result["verification"]["failed_count"] == 1
    assert result["verification"]["failed_commands"] == ["compile-module"]
