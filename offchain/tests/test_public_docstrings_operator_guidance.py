from __future__ import annotations

import ast
from collections import Counter
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest


ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "38367d3ab06ce107bbd5d82902ffb201cdf9eed6"
PYTHON = sys.executable
SUPPORTED_MODULES = {
    "scripts/mission_control.py",
    "scripts/mission_pack_runner.py",
}
EXPECTED_PUBLIC_SYMBOLS = {
    "scripts/mission_control.py": {
        "CommandResult",
        "CommandResult.passed",
        "utc_now",
        "safe_label",
        "ensure_log_dir",
        "write_text",
        "command_to_text",
        "run_command",
        "build_verification_plan",
        "assert_git_clean_before_start",
        "summarize_results",
        "run_verification",
        "main",
    },
    "scripts/mission_pack_runner.py": {
        "FileActionResult",
        "GitActionResult",
        "GitActionResult.passed",
        "utc_now",
        "pushd",
        "read_json",
        "write_json",
        "is_safe_relative_path",
        "resolve_pack_path",
        "scan_content_forbidden_patterns",
        "validate_file_action",
        "validate_pack",
        "render_template",
        "apply_file_action",
        "git_status_short",
        "relative_to_repo",
        "untracked_directory_contains_only_allowed_files",
        "git_status_short_ignoring_allowed_untracked_paths",
        "git_action",
        "git_commit",
        "git_latest_short_commit",
        "run_pack_verification",
        "run_mission_pack",
        "main",
    },
}
REQUIRED_GUIDE_SECTIONS = {
    "Purpose and current boundary",
    "Supported operator commands",
    "Prerequisites",
    "Safe-start checklist",
    "Local verification command",
    "Mission-pack command",
    "Files and outputs",
    "Reading outcomes",
    "Failure and recovery",
    "Git actions and approvals",
    "Actions this guide does not authorize",
    "Related documentation",
}
EXPECTED_REGISTRY_ENTRY = {
    "path": "docs/OPERATOR_GUIDE.md",
    "classification": "CURRENT_INTERNAL",
    "audience": "Project owner, operators, maintainers, and technical reviewers",
    "purpose": (
        "Current safe local operator guidance for supported DeltaGrid "
        "development and verification commands"
    ),
    "authority_level": "CURRENT_SUPPORTING",
    "conflicts_with_current_state": False,
    "test_dependent": True,
    "checksum_dependent": False,
    "referenced_by_other_records": True,
    "ai_tone_severity": 1,
    "readability_severity": 1,
    "recommended_treatment": "LEAVE_UNCHANGED",
    "notes": (
        "Current operator guidance only. It is subordinate to the final freeze "
        "and current policies and does not authorize research, trading, capital, "
        "ML, or autonomous execution."
    ),
}
EXPECTED_CHANGED_PATHS = {
    "docs/OPERATOR_GUIDE.md",
    "docs/README.md",
    "docs/documentation-status.json",
    "offchain/tests/test_current_policy_docs.py",
    "offchain/tests/test_document_status_banners.py",
    "offchain/tests/test_documentation_status.py",
    "offchain/tests/test_human_cli_report_language.py",
    "offchain/tests/test_public_docstrings_operator_guidance.py",
    "offchain/tests/test_research_evidence_summaries.py",
    "scripts/mission_control.py",
    "scripts/mission_pack_runner.py",
}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def base_text(path: str) -> str:
    return git("show", f"{BASE_COMMIT}:{path}").stdout


def current_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def public_inventory(text: str) -> dict[str, ast.AST]:
    inventory: dict[str, ast.AST] = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            inventory[node.name] = node
            for child in node.body:
                if (
                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and not child.name.startswith("_")
                    and any(
                        isinstance(decorator, ast.Name) and decorator.id == "property"
                        for decorator in child.decorator_list
                    )
                ):
                    inventory[f"{node.name}.{child.name}"] = child
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            inventory[node.name] = node
    return inventory


def strip_genuine_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            del node.body[0]
    return ast.fix_missing_locations(tree)


def executable_dump(text: str) -> str:
    return ast.dump(strip_genuine_docstrings(ast.parse(text)), include_attributes=False)


def module_nodes(text: str) -> list[ast.AST]:
    tree = ast.parse(text)
    nodes: list[ast.AST] = [tree]
    nodes.extend(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and (
            not hasattr(node, "name")
            or not node.name.startswith("_")
            or isinstance(node, ast.ClassDef)
        )
    )
    return nodes


def run_script(path: str, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [PYTHON, str(ROOT / path), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_module(module: str, *args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [PYTHON, "-m", module, *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def markdown_links(path: Path) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8"))


def assert_no_positive_authorization(text: str) -> None:
    compact = normalized(text)
    prohibited = {
        "approved for paper trading",
        "paper trading is authorized",
        "live trading is authorized",
        "capital deployment is authorized",
        "ml operation is authorized",
        "autonomous execution is authorized",
        "a validated profitable strategy exists",
        "validated alpha exists",
        "proven alpha",
        "deployment-ready",
        "production-ready trading",
    }
    found = sorted(phrase for phrase in prohibited if phrase in compact)
    assert not found, f"unsafe authorization claim(s): {found}"


def test_supported_module_and_public_symbol_inventory_is_exact() -> None:
    detected = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "scripts").glob("*.py")
        if "argparse.ArgumentParser" in path.read_text(encoding="utf-8")
    }
    assert detected == SUPPORTED_MODULES
    for path in SUPPORTED_MODULES:
        base_inventory = set(public_inventory(base_text(path)))
        current_inventory = set(public_inventory(current_text(path)))
        assert base_inventory == current_inventory == EXPECTED_PUBLIC_SYMBOLS[path]
    assert "from scripts.mission_control import" in current_text(
        "scripts/mission_pack_runner.py"
    )


def test_every_locked_public_symbol_has_a_well_formed_docstring() -> None:
    for path in SUPPORTED_MODULES:
        tree = ast.parse(current_text(path))
        nodes = {"<module>": tree, **public_inventory(current_text(path))}
        for name, node in nodes.items():
            docstring = ast.get_docstring(node, clean=False)
            assert docstring and docstring.strip(), f"missing docstring: {path}:{name}"
            lines = docstring.strip().splitlines()
            summary = lines[0].strip()
            assert summary and len(summary) <= 100
            assert summary.endswith((".", "!", "?"))
            if len(lines) > 1:
                assert lines[1].strip() == "", f"missing summary break: {path}:{name}"


def test_docstrings_remove_mission_branding_and_preserve_authorization_boundaries() -> None:
    combined = "\n".join(
        ast.get_docstring(ast.parse(current_text(path)), clean=False) or ""
        for path in SUPPORTED_MODULES
    )
    assert "Mission 41" not in combined
    assert "Mission 42" not in combined
    assert "development" in combined and "verification" in combined
    assert "not research" in combined and "not a research" in combined
    assert "not establish profitable alpha" in combined
    assert_no_positive_authorization(combined)


def test_nontrivial_docstrings_describe_arguments_results_exceptions_and_side_effects() -> None:
    required_sections = {
        "scripts/mission_control.py": {
            "safe_label": ("Args:", "Returns:"),
            "run_command": ("Args:", "Returns:", "Raises:"),
            "build_verification_plan": ("Args:", "Returns:", "Raises:"),
            "run_verification": ("Args:", "Returns:", "Raises:"),
        },
        "scripts/mission_pack_runner.py": {
            "pushd": ("Args:", "Yields:", "Raises:"),
            "resolve_pack_path": ("Args:", "Returns:", "Raises:"),
            "validate_pack": ("Args:", "Raises:"),
            "apply_file_action": ("Args:", "Returns:", "Raises:"),
            "git_commit": ("Args:", "Returns:"),
            "run_mission_pack": ("Args:", "Returns:", "Raises:"),
        },
    }
    for path, expected in required_sections.items():
        inventory = public_inventory(current_text(path))
        for name, sections in expected.items():
            docstring = ast.get_docstring(inventory[name], clean=False) or ""
            assert all(section in docstring for section in sections)
    control_docs = current_text("scripts/mission_control.py")
    pack_docs = current_text("scripts/mission_pack_runner.py")
    assert "passed directly to ``subprocess.run``" in control_docs
    assert "write its summary" in control_docs
    assert "``git add`` and ``git commit``" in pack_docs
    assert "git push origin main" in pack_docs
    assert "avoid declared file actions and verification commands" in pack_docs


def test_complete_production_asts_are_equal_after_stripping_docstrings() -> None:
    for path in SUPPORTED_MODULES:
        assert ast.dump(ast.parse(base_text(path)), include_attributes=False) != ast.dump(
            ast.parse(current_text(path)), include_attributes=False
        )
        assert executable_dump(base_text(path)) == executable_dump(current_text(path))


def test_signatures_decorators_imports_constants_and_order_are_unchanged() -> None:
    for path in SUPPORTED_MODULES:
        before = ast.parse(base_text(path))
        after = ast.parse(current_text(path))
        before_symbols = public_inventory(base_text(path))
        after_symbols = public_inventory(current_text(path))
        for name in before_symbols:
            old = before_symbols[name]
            new = after_symbols[name]
            assert type(old) is type(new)
            if isinstance(old, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert ast.dump(old.args, include_attributes=False) == ast.dump(
                    new.args, include_attributes=False
                )
                old_return = ast.dump(old.returns, include_attributes=False) if old.returns else None
                new_return = ast.dump(new.returns, include_attributes=False) if new.returns else None
                assert old_return == new_return
            assert [ast.dump(item, include_attributes=False) for item in old.decorator_list] == [
                ast.dump(item, include_attributes=False) for item in new.decorator_list
            ]
        selected = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)
        assert [ast.dump(node, include_attributes=False) for node in before.body if isinstance(node, selected)] == [
            ast.dump(node, include_attributes=False) for node in after.body if isinstance(node, selected)
        ]
        assert executable_dump(base_text(path)) == executable_dump(current_text(path))


def test_docstring_stripper_accepts_only_leading_docstring_changes() -> None:
    before = '''"""Module before."""
class Example:
    """Class before."""
    @property
    def value(self):
        """Property before."""
        return 1
async def operation():
    """Function before."""
    "later executable string"
    return "kept"
'''
    after = before.replace("before", "after")
    assert executable_dump(before) == executable_dump(after)
    assert executable_dump(after) != executable_dump(
        after.replace('"later executable string"', '"changed executable string"')
    )


def test_docstring_stripper_rejects_representative_executable_changes() -> None:
    source = '''import subprocess
DEFAULT_PATH = "reports/original"
def marker(function):
    return function
@marker
def sample(flag=True, path=DEFAULT_PATH):
    if flag:
        subprocess.run(["git", "status"], check=False)
    return path
'''
    changes = (
        source.replace("return path", "return None"),
        source.replace('"status"', '"diff"'),
        source.replace("flag=True", "flag=False"),
        source.replace("if flag:", "if not flag:"),
        source.replace("reports/original", "reports/changed"),
        source.replace("path=DEFAULT_PATH", "path=DEFAULT_PATH, extra=None"),
        source.replace("@marker", "@classmethod"),
    )
    expected = executable_dump(source)
    assert all(executable_dump(changed) != expected for changed in changes)


def test_cli_help_is_byte_identical_to_the_batch_6_base(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    for path in SUPPORTED_MODULES:
        (tmp_path / path).write_text(base_text(path), encoding="utf-8")
    cases = (
        ("scripts.mission_control", ("--help",)),
        ("scripts.mission_control", ("verify", "--help")),
        ("scripts.mission_pack_runner", ("--help",)),
        ("scripts.mission_pack_runner", ("run", "--help")),
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for module, args in cases:
        base = subprocess.run(
            [PYTHON, "-m", module, *args],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        current = subprocess.run(
            [PYTHON, "-m", module, *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert (current.returncode, current.stdout, current.stderr) == (
            base.returncode,
            base.stdout,
            base.stderr,
        )
        assert current.returncode == 0


def test_cli_contracts_machine_output_human_logs_and_exit_codes_are_unchanged() -> None:
    for path in SUPPORTED_MODULES:
        assert executable_dump(base_text(path)) == executable_dump(current_text(path))
    missing_control = run_script("scripts/mission_control.py")
    required_control = run_script("scripts/mission_control.py", "verify")
    missing_pack = run_module("scripts.mission_pack_runner")
    required_pack = run_module("scripts.mission_pack_runner", "run")
    assert [item.returncode for item in (missing_control, required_control, missing_pack, required_pack)] == [2, 2, 2, 2]
    assert "required: command" in missing_control.stderr
    assert "required: --mission" in required_control.stderr
    assert "required: command" in missing_pack.stderr
    assert "required: --pack" in required_pack.stderr
    control = importlib.import_module("scripts.mission_control")
    assert list(inspect.signature(control.run_verification).parameters) == [
        "mission", "module_file", "test_file", "mission_test", "mission_command",
        "log_dir", "skip_full_suite", "require_clean_start", "dry_run",
    ]
    assert list(control.CommandResult.__dataclass_fields__) == [
        "name", "command", "returncode", "stdout", "stderr", "duration_seconds", "log_path"
    ]


def test_operator_guide_is_the_only_new_guide_and_has_every_required_section() -> None:
    guide = ROOT / "docs" / "OPERATOR_GUIDE.md"
    assert guide.is_file()
    assert guide.read_text(encoding="utf-8").startswith("# DeltaGrid operator guide\n")
    headings = set(re.findall(r"^## (.+)$", guide.read_text(encoding="utf-8"), re.MULTILINE))
    assert headings == REQUIRED_GUIDE_SECTIONS
    operator_guides = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "docs").glob("*OPERATOR*GUIDE*.md")
    }
    assert operator_guides == {"docs/OPERATOR_GUIDE.md"}


def test_guide_documents_exact_supported_commands_and_not_historical_interfaces() -> None:
    text = current_text("docs/OPERATOR_GUIDE.md")
    assert text.count("`scripts/mission_control.py`") >= 1
    assert text.count("`scripts/mission_pack_runner.py`") >= 1
    assert "exactly:" in text
    assert "Historical mission modules" in text
    assert "not supported current operator interfaces" in text
    assert "development and verification interfaces" in text


def test_guide_help_examples_run_successfully() -> None:
    guide = current_text("docs/OPERATOR_GUIDE.md")
    direct_commands = (
        ("scripts/mission_control.py", "--help"),
        ("scripts/mission_control.py", "verify", "--help"),
    )
    for command in direct_commands:
        published = "offchain/.venv/bin/python " + " ".join(command)
        assert published in guide
        result = run_script(*command)
        assert result.returncode == 0
        assert result.stderr == ""
    module_commands = (("--help",), ("run", "--help"))
    for arguments in module_commands:
        published = (
            "offchain/.venv/bin/python -m scripts.mission_pack_runner "
            + " ".join(arguments)
        )
        assert published in guide
        result = run_module("scripts.mission_pack_runner", *arguments)
        assert result.returncode == 0
        assert result.stderr == ""
    assert "offchain/.venv/bin/python scripts/mission_pack_runner.py" not in guide


def test_mission_control_guide_dry_run_is_valid_and_writes_only_summary(tmp_path: Path) -> None:
    log_parent = tmp_path / "logs"
    result = run_script(
        "scripts/mission_control.py",
        "verify",
        "--mission", "local-software-review",
        "--module-file", "scripts/mission_control.py",
        "--test-file", "offchain/tests/test_mission_control.py",
        "--mission-test", "offchain/tests/test_mission_control.py",
        "--mission-command", "git diff --check",
        "--log-dir", str(log_parent),
        "--skip-full-suite",
        "--dry-run",
    )
    assert result.returncode == 0 and result.stderr == ""
    summary = json.loads(result.stdout)
    assert summary["global_verdict"] == "MISSION_CONTROL_DRY_RUN"
    assert summary["command_count"] == 6
    artifacts = {path.relative_to(log_parent).as_posix() for path in log_parent.rglob("*") if path.is_file()}
    assert len(artifacts) == 1
    assert next(iter(artifacts)).endswith("/summary.json")


def test_mission_pack_guide_dry_run_applies_nothing_and_runs_nothing(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "__init__.py").write_text("", encoding="utf-8")
    for path in SUPPORTED_MODULES:
        (tmp_path / path).write_text(current_text(path), encoding="utf-8")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / ".git" / "info" / "exclude").write_text(
        "/scripts/\n",
        encoding="utf-8",
    )
    pack_path = tmp_path / "reviewed-local-pack.json"
    target = tmp_path / "generated" / "never-written.txt"
    sentinel = tmp_path / "verification-ran.txt"
    pack_path.write_text(
        json.dumps(
            {
                "mission": "local-pack-review",
                "code_files": [
                    {"path": "generated/never-written.txt", "content": "not applied\n"}
                ],
                "verification": {
                    "mission_command": (
                        f'{PYTHON} -c "from pathlib import Path; '
                        "Path('verification-ran.txt').write_text('bad')\""
                    ),
                    "skip_full_suite": True,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    result = run_module(
        "scripts.mission_pack_runner",
        "run", "--pack", str(pack_path), "--dry-run",
        cwd=tmp_path,
    )
    assert result.returncode == 0 and result.stderr == ""
    summary = json.loads(result.stdout)
    assert summary["global_verdict"] == "MISSION_PACK_RUNNER_DRY_RUN"
    assert summary["code_file_results"][0]["reason"] == "dry-run"
    assert summary["verification"] == {}
    assert "verification_plan" in summary
    assert not target.exists() and not sentinel.exists()
    artifacts = {
        path.relative_to(tmp_path).as_posix()
        for path in (tmp_path / "reports" / "mission_logs").rglob("*")
        if path.is_file()
    }
    assert len(artifacts) == 1 and next(iter(artifacts)).endswith("/summary.json")


def test_guide_uses_project_python_and_explains_every_cli_option() -> None:
    text = current_text("docs/OPERATOR_GUIDE.md")
    assert "offchain/.venv/bin/python" in text
    options = {
        "--mission", "--module-file", "--test-file", "--mission-test",
        "--mission-command", "--log-dir", "--skip-full-suite",
        "--require-clean-start", "--dry-run", "--pack", "--repo-root",
        "--commit", "--push", "--no-clean-start",
    }
    for option in options:
        assert f"`{option}`" in text
    assert "not through a shell" in text
    assert "default is `reports/mission_logs`" in text


def test_guide_accurately_explains_outputs_and_outcomes() -> None:
    text = normalized(current_text("docs/OPERATOR_GUIDE.md")).replace("*", "")
    for phrase in (
        "reports/mission_logs",
        "summary.json",
        "machine-stable command details",
        "formatted json to stdout",
        "pass means a software or verification step",
        "fail means a command or software requirement failed",
        "reject means a research hypothesis or candidate missed a frozen research gate",
        "stop means execution deliberately halted",
        "blocked or not authorized means a later stage cannot proceed",
        "pass does not imply profitability",
    ):
        assert phrase in text


def test_guide_binds_every_current_boundary_to_its_prohibition() -> None:
    text = normalized(current_text("docs/OPERATOR_GUIDE.md"))
    required = (
        "new research is not reopened by this guide",
        "paper trading is not currently authorized",
        "live trading is not authorized",
        "capital deployment is blocked",
        "ml operation is not authorized",
        "autonomous execution is not authorized",
        "validation or holdout access is not authorized",
        "private-key use, and account access are not authorized",
        "cannot independently change authorization",
    )
    assert all(statement in text for statement in required)
    assert_no_positive_authorization(text)


def test_guide_requires_git_approval_and_safe_recovery() -> None:
    text = normalized(current_text("docs/OPERATOR_GUIDE.md")).replace("`", "")
    assert "--commit and --push are repository operations and require explicit approval" in text
    assert "--no-clean-start" in text and "weakens a safety check" in text
    assert "automatic push is not a safe default workflow" in text
    assert "explicit --push targets origin main" in text
    assert "stop if the remote has moved" in text
    assert "provides no force-push workflow" in text
    assert "do not bypass safety gates merely to obtain pass" in text
    for unsafe in ("git reset --hard", "force-push as", "delete evidence", "discard unknown work"):
        assert unsafe not in text


def test_all_operator_guide_links_resolve() -> None:
    guide = ROOT / "docs" / "OPERATOR_GUIDE.md"
    for link in markdown_links(guide):
        target_text, _, _fragment = link.partition("#")
        if "://" in target_text or target_text.startswith("mailto:"):
            continue
        target = guide if not target_text else guide.parent / unquote(target_text)
        assert target.exists(), f"broken operator-guide link: {link}"


def test_docs_home_links_current_operator_guidance_without_authorization() -> None:
    text = normalized(current_text("docs/README.md"))
    assert "[operator guide](operator_guide.md)" in text
    assert "two supported current local development and verification commands" in text
    assert "safe dry-run use, local logs, repository actions, and failure handling" in text
    assert "public docstrings for those supported operator modules are also current" in text
    assert "the guide does not authorize research or trading" in text
    assert "does not establish profitable alpha or authorize paper trading" in text


def test_registry_has_exact_operator_entry_count_and_classifications() -> None:
    registry = json.loads(current_text("docs/documentation-status.json"))
    by_path = {item["path"]: item for item in registry["documents"]}
    counts = Counter(item["classification"] for item in registry["documents"])
    assert len(by_path) == 166
    assert counts == {
        "CURRENT_PUBLIC": 10,
        "CURRENT_INTERNAL": 5,
        "HISTORICAL": 97,
        "SUPERSEDED": 8,
        "DESIGN_ONLY": 2,
        "EVIDENCE_IMMUTABLE": 10,
        "MACHINE_REFERENCE": 34,
    }
    assert by_path["docs/OPERATOR_GUIDE.md"] == EXPECTED_REGISTRY_ENTRY
    assert "does not authorize" in normalized(by_path["docs/OPERATOR_GUIDE.md"]["notes"])


def test_registry_diff_is_exactly_one_parsed_value_entry() -> None:
    base = json.loads(base_text("docs/documentation-status.json"))
    current = json.loads(current_text("docs/documentation-status.json"))
    base_by_path = {item["path"]: item for item in base["documents"]}
    current_by_path = {item["path"]: item for item in current["documents"]}
    assert len(base_by_path) == 165 and len(current_by_path) == 166
    assert current_by_path.keys() - base_by_path.keys() == {"docs/OPERATOR_GUIDE.md"}
    assert all(current_by_path[path] == item for path, item in base_by_path.items())
    assert {key: value for key, value in current.items() if key != "documents"} == {
        key: value for key, value in base.items() if key != "documents"
    }


def test_protected_files_dependencies_and_other_json_are_unchanged() -> None:
    changed = set(git("diff", "--name-only", BASE_COMMIT, "--").stdout.splitlines())
    changed.update(git("ls-files", "--others", "--exclude-standard").stdout.splitlines())
    assert changed == EXPECTED_CHANGED_PATHS
    tracked = git("ls-tree", "-r", "--name-only", BASE_COMMIT).stdout.splitlines()
    for path in tracked:
        if path in EXPECTED_CHANGED_PATHS:
            continue
        assert (ROOT / path).read_bytes() == subprocess.run(
            ["git", "show", f"{BASE_COMMIT}:{path}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    changed_json = {path for path in changed if path.endswith(".json")}
    assert changed_json == {"docs/documentation-status.json"}
    assert current_text("offchain/requirements.txt") == base_text("offchain/requirements.txt")


def test_no_new_cli_entry_point_or_absolute_test_dependency_exists() -> None:
    base_clis = {
        path
        for path in git("ls-tree", "-r", "--name-only", BASE_COMMIT).stdout.splitlines()
        if path.endswith(".py")
        and not path.startswith("offchain/tests/")
        and "argparse.ArgumentParser" in base_text(path)
    }
    current_clis = {
        path
        for path in git("ls-files", "*.py").stdout.splitlines()
        if not path.startswith("offchain/tests/")
        and "argparse.ArgumentParser" in current_text(path)
    }
    assert current_clis == base_clis
    own_text = Path(__file__).read_text(encoding="utf-8")
    assert ("/" + "Users" + "/") not in own_text


def test_unsafe_positive_authorization_wording_fails_negative_controls() -> None:
    assert_no_positive_authorization(
        "Paper trading is not currently authorized; capital deployment is blocked."
    )
    unsafe = (
        "The system is approved for paper trading.",
        "Live trading is authorized after PASS.",
        "Capital deployment is authorized by this dashboard.",
        "A validated profitable strategy exists.",
        "This command proves alpha and is deployment-ready.",
    )
    for sample in unsafe:
        with pytest.raises(AssertionError):
            assert_no_positive_authorization(sample)
