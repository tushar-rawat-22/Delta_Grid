from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import hashlib
import http.client
import json
from pathlib import Path
import re
import shutil
import threading
from urllib.parse import urlsplit

import pytest

from offchain.research.admission import (
    DatasetResolver,
    ResearchAdmissionService,
    TrialLedger,
    canonical_hash,
    canonical_json,
)
from offchain.research.control_plane import (
    ReadOnlyTrialLedger,
    ResearchControlPlaneService,
)
from offchain.research.engine_service import CanonicalResultEngineService
import offchain.research.cockpit as public_api
from offchain.research.cockpit import (
    MISSION_AUTHORIZATION_STAGE,
    MISSION_BASE_COMMIT,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    CockpitConfig,
    CockpitError,
    DemoSnapshotSource,
    LiveSnapshotSource,
    ResearchCockpitApplication,
    ResearchCockpitServer,
)
from offchain.research.cockpit.server import SECURITY_HEADERS, _display_safe
from offchain.tests.test_canonical_result_engine_service import (
    catalog_for,
    fixture_bytes,
    request_value,
)


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "offchain" / "research" / "cockpit"
CONTRACT_PATH = ROOT / "contracts" / "DELTAGRID_RESEARCH_COCKPIT_UI_V1.json"
HTML_PATH = PACKAGE / "static" / "index.html"
CSS_PATH = PACKAGE / "static" / "app.css"
JS_PATH = PACKAGE / "static" / "app.js"
COMMIT = "e26eea3348a7f7f502e85baf4ad7c2ad896399f6"
EXPECTED_EXPORTS = {
    "CockpitError",
    "CockpitConfig",
    "ResearchCockpitApplication",
    "ResearchCockpitServer",
    "DemoSnapshotSource",
    "LiveSnapshotSource",
    "MISSION_CONTRACT_ID",
    "MISSION_CONTRACT_HASH",
    "MISSION_BASE_COMMIT",
    "MISSION_AUTHORIZATION_STAGE",
}
EXPECTED_PACKAGE_FILES = {
    "offchain/research/cockpit/__init__.py",
    "offchain/research/cockpit/__main__.py",
    "offchain/research/cockpit/models.py",
    "offchain/research/cockpit/sources.py",
    "offchain/research/cockpit/server.py",
    "offchain/research/cockpit/static/index.html",
    "offchain/research/cockpit/static/app.css",
    "offchain/research/cockpit/static/app.js",
    "offchain/research/cockpit/demo/healthy_snapshot.json",
    "offchain/research/cockpit/demo/degraded_snapshot.json",
}
EXPECTED_AUTHORIZED = {
    "local_browser_interface_authorized",
    "loopback_only_http_serving_authorized",
    "mission_96a_snapshot_loading_authorized",
    "research_control_plane_service_connected_mode_authorized",
    "fixed_hash_verified_demo_snapshot_loading_authorized",
    "deterministic_presentation_projection_authorized",
    "client_side_text_and_status_filtering_authorized",
    "standard_library_webbrowser_opening_authorized",
    "local_static_html_css_javascript_authorized",
    "read_only_operator_observation_authorized",
    "ui_and_server_tests_authorized",
}
EXPECTED_FALSE = {
    "remote_binding_authorized",
    "lan_exposure_authorized",
    "public_hosting_authorized",
    "cloud_deployment_authorized",
    "analytics_authorized",
    "telemetry_authorized",
    "external_assets_authorized",
    "external_fonts_authorized",
    "cdn_use_authorized",
    "external_api_requests_authorized",
    "ledger_write_authorized",
    "database_creation_authorized",
    "trial_reservation_authorized",
    "trial_admission_authorized",
    "lifecycle_mutation_authorized",
    "result_finalization_authorized",
    "control_execution_authorized",
    "fixture_loading_in_cockpit_runtime_authorized",
    "quantitative_metric_recalculation_authorized",
    "strategy_research_authorized",
    "development_market_evaluation_authorized",
    "validation_access_authorized",
    "holdout_access_authorized",
    "protected_data_access_authorized",
    "model_training_authorized",
    "model_promotion_authorized",
    "signal_generation_authorized",
    "portfolio_construction_authorized",
    "exchange_access_authorized",
    "credential_access_authorized",
    "paper_trading_authorized",
    "live_trading_authorized",
    "capital_deployment_authorized",
    "autonomous_research_authorized",
    "autonomous_promotion_authorized",
    "autonomous_execution_authorized",
}


def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def demo_value(scenario: str) -> dict:
    return json.loads((PACKAGE / "demo" / f"{scenario}_snapshot.json").read_bytes())


class RunningServer:
    def __init__(self) -> None:
        self.server = ResearchCockpitServer(
            ResearchCockpitApplication(CockpitConfig(port=0))
        )
        self.bootstrap_url = self.server.start()
        self.parsed = urlsplit(self.bootstrap_url)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", self.parsed.port)
        connection.request(
            "GET",
            self.parsed.path,
            headers={"Host": f"127.0.0.1:{self.parsed.port}"},
        )
        response = connection.getresponse()
        response.read()
        self.bootstrap_status = response.status
        self.cookie_header = response.getheader("Set-Cookie")
        self.cookie = self.cookie_header.split(";", 1)[0]
        connection.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        cookie: str | None = None,
        host: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.parsed.port)
        headers = {
            "Host": host or f"127.0.0.1:{self.parsed.port}",
        }
        if cookie is not None:
            headers["Cookie"] = cookie
        if extra:
            headers.update(extra)
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), body
        connection.close()
        return result

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)


@pytest.fixture
def running_server():
    value = RunningServer()
    try:
        yield value
    finally:
        value.close()


def test_contract_identity_hash_predecessor_and_exact_authority() -> None:
    value = contract()
    core = dict(value)
    supplied = core.pop("contract_hash_sha256")
    assert value["contract_id"] == MISSION_CONTRACT_ID
    assert value["contract_version"] == 1
    assert value["base_commit"] == MISSION_BASE_COMMIT == COMMIT
    assert value["authorization_stage"] == MISSION_AUTHORIZATION_STAGE
    assert value["preceding_contract"] == (
        "contracts/DELTAGRID_RESEARCH_CONTROL_PLANE_V1.json"
    )
    assert value["preceding_contract_hash_sha256"] == (
        "c1e0c8c55db90fe8a81d3afe2d243537c703dbee6a945596f4b37c5ee13e70a9"
    )
    assert canonical_hash(core) == supplied == MISSION_CONTRACT_HASH
    assert set(value["implementation_authorization"]) == EXPECTED_AUTHORIZED
    assert set(value["implementation_authorization"].values()) == {True}
    assert set(value["authorization_state"]) == EXPECTED_FALSE
    assert set(value["authorization_state"].values()) == {False}


def test_exact_package_inventory_and_public_exports() -> None:
    actual = {
        path.relative_to(ROOT).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    assert actual == EXPECTED_PACKAGE_FILES
    assert set(public_api.__all__) == EXPECTED_EXPORTS


def test_python_boundary_uses_no_new_dependencies_clients_sql_or_writes() -> None:
    allowed_roots = {
        "__future__",
        "argparse",
        "dataclasses",
        "datetime",
        "hashlib",
        "hmac",
        "http",
        "json",
        "models",
        "pathlib",
        "re",
        "secrets",
        "server",
        "sources",
        "sys",
        "threading",
        "types",
        "typing",
        "urllib",
        "webbrowser",
        "offchain",
    }
    forbidden_imports = {
        "sqlite3",
        "subprocess",
        "requests",
        "urllib3",
        "httpx",
        "aiohttp",
        "socket",
    }
    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
                assert not any(alias.name == "TrialLedger" for alias in node.names)
        assert {name.split(".", 1)[0] for name in imported} <= allowed_roots
        assert not ({name.split(".", 1)[0] for name in imported} & forbidden_imports)
    assert not any(
        path.name in {"requirements.txt", "pyproject.toml", "poetry.lock"}
        for path in PACKAGE.rglob("*")
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"port": -1},
        {"port": 65536},
        {"port": True},
        {"refresh_seconds": 4},
        {"refresh_seconds": 3601},
        {"refresh_seconds": True},
        {"mode": "connected", "demo_scenario": None},
        {"mode": "demo", "demo_scenario": "unknown"},
        {"mode": "demo", "ledger_path": "ledger.sqlite3"},
    ],
)
def test_configuration_rejects_invalid_mode_specific_values(updates: dict) -> None:
    with pytest.raises(CockpitError) as caught:
        CockpitConfig(**updates)
    assert caught.value.reason_token == "COCKPIT_CONFIGURATION_INVALID"


def test_connected_configuration_requires_all_values_and_is_immutable() -> None:
    config = CockpitConfig(
        mode="connected",
        demo_scenario=None,
        ledger_path="/tmp/ledger",
        result_root_path="/tmp/results",
        repository_root_path="/tmp/repository",
        expected_repository_commit="a" * 40,
    )
    assert config.mode == "CONNECTED"
    with pytest.raises(FrozenInstanceError):
        config.port = 80
    with pytest.raises(CockpitError):
        CockpitConfig(
            mode="connected",
            demo_scenario=None,
            ledger_path="/tmp/ledger",
            result_root_path="/tmp/results",
            repository_root_path="/tmp/repository",
            expected_repository_commit="A" * 40,
        )


def test_demo_hash_identity_health_and_canonical_json() -> None:
    declarations = contract()["demonstration_snapshots"]
    for scenario in ("healthy", "degraded"):
        path = PACKAGE / "demo" / f"{scenario}_snapshot.json"
        raw = path.read_bytes()
        value = json.loads(raw)
        core = dict(value)
        supplied = core.pop("canonical_snapshot_hash")
        expected = declarations[scenario]
        assert hashlib.sha256(raw).hexdigest() == expected["byte_sha256"]
        assert canonical_json(value).encode("utf-8") == raw
        assert canonical_hash(core) == supplied == expected["canonical_snapshot_hash"]
        assert value["snapshot_id"] == expected["snapshot_id"]
        assert value["system"]["health_token"] == expected["health_token"]
        assert len(value["trials"]) == expected["trial_count"]
        assert len(value["results"]) == expected["verified_result_count"]
        assert len(value["incidents"]) == expected["incident_count"]
    healthy = demo_value("healthy")
    degraded = demo_value("degraded")
    assert healthy["system"]["health_token"] == "HEALTHY"
    assert healthy["system"]["verified_linked_result_count"] == 1
    assert healthy["incidents"] == []
    assert degraded["system"]["health_token"] == "DEGRADED"
    assert {item["category"] for item in degraded["incidents"]} == {
        "COMPLETED_WITHOUT_RESULT_LINK"
    }


def _generate_demo(location: Path, *, degraded: bool) -> dict:
    fixture_raw = fixture_bytes()
    content_hash = hashlib.sha256(fixture_raw).hexdigest()
    artifact_root = location / "artifacts"
    fixture_path = artifact_root / "fixtures" / "synthetic.json"
    fixture_path.parent.mkdir(parents=True)
    fixture_path.write_bytes(fixture_raw)
    resolver = DatasetResolver(catalog_for(content_hash), artifact_root)
    ledger = TrialLedger(location / "trials.sqlite3")
    request = request_value(content_hash)
    request["repository_commit"] = COMMIT
    request["canonical_request_hash"] = canonical_hash(
        {
            key: item
            for key, item in request.items()
            if key != "canonical_request_hash"
        }
    )
    ledger.register_budget(
        budget_id=request["budget_id"],
        controlling_contract_id=request["controlling_contract_id"],
        controlling_contract_hash=request["controlling_contract_hash"],
        experiment_family="MISSION_95_SYNTHETIC_CONTROLS",
        total_trial_budget=8,
        created_at="2026-08-03T00:00:00Z",
    )
    admission = ResearchAdmissionService(
        controlling_contract_id=request["controlling_contract_id"],
        controlling_contract_hash=request["controlling_contract_hash"],
        repository_commit=COMMIT,
        dataset_resolver=resolver,
        trial_ledger=ledger,
    )
    decision = admission.admit(request)
    engine = CanonicalResultEngineService(
        expected_repository_commit=COMMIT,
        dataset_resolver=resolver,
        trial_ledger=ledger,
        result_root=location / "results",
    )
    engine.execute(request, decision)
    fixture_path.unlink()
    if degraded:
        reservation = ledger.reserve(
            budget_id=request["budget_id"],
            declared_trial_number=2,
            request_hash="c" * 64,
            initiated_by="OPERATOR",
            reserved_at="2026-08-03T00:20:00Z",
            controlling_contract_id=request["controlling_contract_id"],
            controlling_contract_hash=request["controlling_contract_hash"],
        )
        ledger.append_event(
            trial_id=reservation.trial_id,
            status_token="ADMITTED",
            reason_token="ADMISSION_GATES_PASSED",
            event_timestamp="2026-08-03T00:21:00Z",
        )
        ledger.append_event(
            trial_id=reservation.trial_id,
            status_token="COMPLETED",
            reason_token="GENERIC_COMPLETION",
            event_timestamp="2026-08-03T00:22:00Z",
        )
    return ResearchControlPlaneService(
        ledger=ReadOnlyTrialLedger(ledger.database_path),
        result_root=engine.result_root,
        repository_root=ROOT,
        expected_repository_commit=COMMIT,
    ).build_snapshot(
        as_of=(
            "2026-08-03T12:05:00Z"
            if degraded
            else "2026-08-03T12:00:00Z"
        )
    ).as_dict()


def test_demo_snapshots_regenerate_through_missions_94_95_and_96a() -> None:
    temporary = Path("/private/tmp/deltagrid-mission96b-demo")
    assert not temporary.exists()
    try:
        healthy = _generate_demo(temporary / "healthy", degraded=False)
        degraded = _generate_demo(temporary / "degraded", degraded=True)
        declarations = contract()["demonstration_snapshots"]
        assert healthy["canonical_snapshot_hash"] == declarations["healthy"][
            "canonical_snapshot_hash"
        ]
        assert healthy["snapshot_id"] == declarations["healthy"]["snapshot_id"]
        assert degraded["canonical_snapshot_hash"] == declarations["degraded"][
            "canonical_snapshot_hash"
        ]
        assert degraded["snapshot_id"] == declarations["degraded"]["snapshot_id"]
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def test_demo_source_detaches_values_rejects_scenario_and_symlink(
    tmp_path: Path,
) -> None:
    source = DemoSnapshotSource()
    first = source.snapshot("healthy")
    first["system"]["health_token"] = "MUTATED"
    assert source.snapshot("HEALTHY")["system"]["health_token"] == "HEALTHY"
    with pytest.raises(CockpitError) as caught:
        source.snapshot("other")
    assert caught.value.reason_token == "DEMO_SCENARIO_INVALID"

    package = tmp_path / "cockpit"
    shutil.copytree(PACKAGE / "demo", package / "demo")
    healthy = package / "demo" / "healthy_snapshot.json"
    healthy.unlink()
    healthy.symlink_to(PACKAGE / "demo" / "healthy_snapshot.json")
    with pytest.raises(CockpitError) as caught:
        DemoSnapshotSource(package_root=package)
    assert caught.value.reason_token == "SNAPSHOT_INTEGRITY_FAILURE"


def test_live_source_fixed_clock_and_utc_format(tmp_path: Path) -> None:
    from offchain.tests.test_research_control_plane import make_ledger

    _, ledger_path, _ = make_ledger(tmp_path)
    result_root = tmp_path / "results"
    result_root.mkdir()
    service = ResearchControlPlaneService(
        ledger=ReadOnlyTrialLedger(ledger_path),
        result_root=result_root,
        repository_root=ROOT,
        expected_repository_commit=COMMIT,
    )
    source = LiveSnapshotSource(
        service,
        clock=lambda: datetime(
            2026, 8, 3, 12, 0, 0, 123456, tzinfo=timezone.utc
        ),
    )
    assert source.snapshot()["system"]["as_of"] == "2026-08-03T12:00:00.123456Z"
    source_zero = LiveSnapshotSource(
        service,
        clock=lambda: datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
    )
    assert source_zero.snapshot()["system"]["as_of"] == "2026-08-03T12:00:00Z"


def test_integer_safety_preserves_types_digits_and_rejects_float() -> None:
    value = _display_safe(
        {
            "large": 9_223_372_036_854_775_807,
            "negative": -12,
            "boolean": True,
            "nothing": None,
            "text": "7",
            "array": [1, False],
        }
    )
    assert value == {
        "large": "9223372036854775807",
        "negative": "-12",
        "boolean": True,
        "nothing": None,
        "text": "7",
        "array": ["1", False],
    }
    with pytest.raises(CockpitError) as caught:
        _display_safe({"float": 1.5})
    assert caught.value.reason_token == "SNAPSHOT_INTEGRITY_FAILURE"


def test_application_envelopes_are_detached_ordered_and_path_safe() -> None:
    application = ResearchCockpitApplication(CockpitConfig())
    envelope = application.snapshot_envelope()
    snapshot = demo_value("healthy")
    assert envelope["schema_version"] == "1.0"
    assert envelope["cockpit_mode"] == "DEMO"
    assert envelope["demo_scenario"] == "HEALTHY"
    assert envelope["integer_encoding"] == "DECIMAL_STRING"
    assert [item["trial_id"] for item in envelope["snapshot"]["trials"]] == [
        item["trial_id"] for item in snapshot["trials"]
    ]
    assert [item["trial_id"] for item in envelope["snapshot"]["results"]] == [
        item["trial_id"] for item in snapshot["results"]
    ]
    assert envelope["snapshot_identity"] == {
        "snapshot_id": snapshot["snapshot_id"],
        "canonical_snapshot_hash": snapshot["canonical_snapshot_hash"],
    }
    serialized = json.dumps(application.meta_envelope())
    assert str(ROOT) not in serialized
    assert "/private/tmp" not in serialized
    assert "session" not in application.meta_envelope()


def test_bootstrap_is_one_time_and_cookie_is_strict(running_server: RunningServer) -> None:
    assert running_server.bootstrap_status == 303
    cookie = running_server.cookie_header
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Path=/" in cookie
    assert "Secure" not in cookie
    assert "Expires" not in cookie
    assert "Max-Age" not in cookie
    status, _, body = running_server.request(
        "GET", running_server.parsed.path
    )
    assert status == 403
    assert json.loads(body)["error"]["reason_token"] == "SESSION_BOOTSTRAP_INVALID"


def test_missing_invalid_session_and_host_fail_closed(
    running_server: RunningServer,
) -> None:
    status, _, body = running_server.request("GET", "/")
    assert status == 403
    assert json.loads(body)["error"]["reason_token"] == "SESSION_REQUIRED"
    status, _, body = running_server.request(
        "GET", "/", cookie="deltagrid_cockpit_session=wrong"
    )
    assert status == 403
    assert json.loads(body)["error"]["reason_token"] == "SESSION_INVALID"
    status, _, body = running_server.request(
        "GET",
        "/",
        cookie=running_server.cookie,
        host=f"0.0.0.0:{running_server.parsed.port}",
    )
    assert status == 400
    assert json.loads(body)["error"]["reason_token"] == "HOST_INVALID"


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/", "text/html; charset=utf-8"),
        ("/assets/app.css", "text/css; charset=utf-8"),
        ("/assets/app.js", "text/javascript; charset=utf-8"),
        ("/api/v1/meta", "application/json; charset=utf-8"),
        ("/api/v1/snapshot", "application/json; charset=utf-8"),
    ],
)
def test_get_and_head_allowlist_content_types_headers_and_no_cors(
    running_server: RunningServer,
    path: str,
    content_type: str,
) -> None:
    for method in ("GET", "HEAD"):
        status, headers, body = running_server.request(
            method, path, cookie=running_server.cookie
        )
        assert status == 200
        assert headers["Content-Type"] == content_type
        assert "Access-Control-Allow-Origin" not in headers
        assert "unsafe-inline" not in headers["Content-Security-Policy"]
        assert "unsafe-eval" not in headers["Content-Security-Policy"]
        for key, value in SECURITY_HEADERS.items():
            assert headers[key] == value
        if method == "HEAD":
            assert body == b""


@pytest.mark.parametrize(
    "method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"]
)
def test_every_write_or_extension_method_is_405(
    running_server: RunningServer, method: str
) -> None:
    status, headers, body = running_server.request(method, "/api/v1/snapshot")
    assert status == 405
    assert headers["Allow"] == "GET, HEAD"
    assert json.loads(body)["error"]["reason_token"] == "METHOD_NOT_ALLOWED"


def test_routes_targets_forwarded_headers_and_generic_errors(
    running_server: RunningServer,
) -> None:
    status, _, body = running_server.request(
        "GET", "/missing", cookie=running_server.cookie
    )
    assert status == 404
    assert json.loads(body)["error"]["reason_token"] == "ROUTE_NOT_FOUND"
    status, _, _ = running_server.request(
        "GET",
        "/api/v1/meta",
        cookie=running_server.cookie,
        extra={
            "Forwarded": "host=example.com",
            "X-Forwarded-Host": "example.com",
            "X-Forwarded-For": "203.0.113.1",
            "X-Real-IP": "203.0.113.1",
        },
    )
    assert status == 200
    status, _, body = running_server.request(
        "GET",
        "/api/v1/snapshot?scenario=unknown",
        cookie=running_server.cookie,
    )
    assert status == 400
    value = json.loads(body)
    assert value == {
        "schema_version": "1.0",
        "error": {
            "reason_token": "DEMO_SCENARIO_INVALID",
            "human_explanation": "The demonstration scenario is invalid.",
        },
    }
    assert str(ROOT).encode() not in body
    assert b"Traceback" not in body


def test_server_is_exact_loopback_and_shutdown_leaves_no_thread(
    running_server: RunningServer,
) -> None:
    assert running_server.server.address == ("127.0.0.1", running_server.parsed.port)
    assert running_server.thread.is_alive()
    running_server.close()
    assert not running_server.thread.is_alive()


def test_static_security_state_and_required_interface_copy() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")
    script = JS_PATH.read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)", html, re.IGNORECASE)
    assert "<style" not in html.lower()
    assert not re.search(r"\sstyle\s*=", html, re.IGNORECASE)
    assert not re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE)
    for forbidden in (
        "innerHTML",
        "outerHTML",
        "insertAdjacentHTML",
        "eval(",
        "new Function",
        "document.write",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "serviceWorker",
        "parseInt",
        "parseFloat",
        "BigInt",
    ):
        assert forbidden not in script
    combined = html + css + script
    assert not re.search(r"https?://|//[A-Za-z0-9]", combined)
    assert "@font-face" not in css
    for text in (
        "DELTAGRID",
        "Research Cockpit v0",
        "System Overview",
        "Authority Matrix",
        "Trial Registry",
        "Result Inspector",
        "Incident Panel",
        "Governance and Contract Chain",
        "Evidence and Warnings",
        "DEMO — SYNTHETIC NON-ALPHA EVIDENCE",
        "DEMONSTRATION INCIDENT — NOT A CURRENT SYSTEM FAILURE",
        "CONNECTED LOCAL READ-ONLY OBSERVATION",
        "Passing software verification does not establish a profitable strategy.",
    ):
        assert text in combined
    assert "aria-live" in html
    assert ":focus-visible" in css
    assert 'cache: "no-store"' in script
    assert "state.refreshing" in script


def test_browser_opening_source_is_after_successful_listen_and_targets_bootstrap() -> None:
    text = (PACKAGE / "__main__.py").read_text(encoding="utf-8")
    start = text.index("bootstrap_url = server.start()")
    opened = text.index("webbrowser.open(bootstrap_url)")
    serving = text.index("server.serve_forever()")
    assert start < opened < serving
    assert "webbrowser.open(" in text
    assert "127.0.0.1" not in text


def test_demo_runtime_has_no_admission_engine_fixture_or_ledger_symbols() -> None:
    runtime = "\n".join(
        (PACKAGE / name).read_text(encoding="utf-8")
        for name in ("models.py", "sources.py", "server.py", "__main__.py")
    )
    for forbidden in (
        "ResearchAdmissionService",
        "CanonicalResultEngineService",
        "SyntheticFixture",
        "sqlite3",
    ):
        assert forbidden not in runtime
    assert "ReadOnlyTrialLedger" in runtime
    assert "ResearchControlPlaneService" in runtime
