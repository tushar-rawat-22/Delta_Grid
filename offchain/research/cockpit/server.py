"""Loopback-only HTTP composition for the Mission 96B research cockpit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import threading
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

from offchain.research.control_plane import (
    ControlPlaneError,
    ReadOnlyTrialLedger,
    ResearchControlPlaneService,
)

from .models import (
    MISSION_AUTHORIZATION_STAGE,
    MISSION_CONTRACT_HASH,
    MISSION_CONTRACT_ID,
    CockpitConfig,
    CockpitError,
)
from .sources import DemoSnapshotSource, LiveSnapshotSource


BIND_ADDRESS = "127.0.0.1"
UI_VERSION = "0"
_COOKIE_NAME = "deltagrid_cockpit_session"
_MAX_REQUEST_TARGET = 2_048
_CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'none'; "
    "object-src 'none'; "
    "media-src 'none'; "
    "worker-src 'none'; "
    "manifest-src 'none'; "
    "frame-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)
SECURITY_HEADERS = MappingProxyType(
    {
        "Content-Security-Policy": _CSP,
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
    }
)
_CONTENT_TYPES = MappingProxyType(
    {
        "/": "text/html; charset=utf-8",
        "/assets/app.css": "text/css; charset=utf-8",
        "/assets/app.js": "text/javascript; charset=utf-8",
        "/api/v1/meta": "application/json; charset=utf-8",
        "/api/v1/snapshot": "application/json; charset=utf-8",
    }
)
_NON_SESSION_ROUTES = frozenset(_CONTENT_TYPES)
_WRITE_METHODS = frozenset(
    {"POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"}
)
_AUTHORIZED_UI_CAPABILITIES = MappingProxyType(
    {
        "local_browser_interface_authorized": True,
        "loopback_only_http_serving_authorized": True,
        "mission_96a_snapshot_loading_authorized": True,
        "research_control_plane_service_connected_mode_authorized": True,
        "fixed_hash_verified_demo_loading_authorized": True,
        "deterministic_presentation_projection_authorized": True,
        "client_side_text_and_status_filtering_authorized": True,
        "standard_library_browser_opening_authorized": True,
        "local_static_html_css_javascript_authorized": True,
        "read_only_operator_observation_authorized": True,
        "ui_and_server_tests_authorized": True,
    }
)
_PROHIBITED_CAPABILITIES = MappingProxyType(
    {
        "remote_binding_authorized": False,
        "lan_exposure_authorized": False,
        "public_hosting_authorized": False,
        "cloud_deployment_authorized": False,
        "analytics_authorized": False,
        "telemetry_authorized": False,
        "external_assets_authorized": False,
        "external_fonts_authorized": False,
        "cdn_use_authorized": False,
        "external_api_requests_authorized": False,
        "ledger_write_authorized": False,
        "database_creation_authorized": False,
        "trial_reservation_authorized": False,
        "trial_admission_authorized": False,
        "lifecycle_mutation_authorized": False,
        "result_finalization_authorized": False,
        "control_execution_authorized": False,
        "fixture_loading_in_cockpit_runtime_authorized": False,
        "quantitative_metric_recalculation_authorized": False,
        "strategy_research_authorized": False,
        "development_market_evaluation_authorized": False,
        "validation_access_authorized": False,
        "holdout_access_authorized": False,
        "protected_data_access_authorized": False,
        "model_training_authorized": False,
        "model_promotion_authorized": False,
        "signal_generation_authorized": False,
        "portfolio_construction_authorized": False,
        "exchange_access_authorized": False,
        "credential_access_authorized": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
        "capital_deployment_authorized": False,
        "autonomous_research_authorized": False,
        "autonomous_promotion_authorized": False,
        "autonomous_execution_authorized": False,
    }
)


def _detached(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )


def _display_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if type(value) is int:
        return str(value)
    if isinstance(value, float):
        raise CockpitError(
            "SNAPSHOT_INTEGRITY_FAILURE",
            "Floating-point values cannot be presented by the cockpit.",
        )
    if isinstance(value, Mapping):
        return {str(key): _display_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_display_safe(item) for item in value]
    raise CockpitError(
        "SNAPSHOT_INTEGRITY_FAILURE",
        "The snapshot contains a value that cannot be presented safely.",
    )


class ResearchCockpitApplication:
    """Immutable presentation boundary over one validated snapshot source."""

    __slots__ = ("_config", "_source", "_static", "_sealed")

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("ResearchCockpitApplication is immutable")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        config: CockpitConfig,
        *,
        source: DemoSnapshotSource | LiveSnapshotSource | None = None,
        clock: Any = None,
    ) -> None:
        if not isinstance(config, CockpitConfig):
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "A validated CockpitConfig is required.",
            )
        try:
            if source is None and config.mode == "DEMO":
                source = DemoSnapshotSource()
            elif source is None:
                ledger = ReadOnlyTrialLedger(config.ledger_path)
                service = ResearchControlPlaneService(
                    ledger=ledger,
                    result_root=config.result_root_path,
                    repository_root=config.repository_root_path,
                    expected_repository_commit=config.expected_repository_commit,
                )
                source = (
                    LiveSnapshotSource(service)
                    if clock is None
                    else LiveSnapshotSource(service, clock=clock)
                )
        except CockpitError:
            raise
        except ControlPlaneError as error:
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "Connected Mission 96A resources could not be initialized.",
            ) from error
        if (
            config.mode == "DEMO"
            and not isinstance(source, DemoSnapshotSource)
        ) or (
            config.mode == "CONNECTED"
            and not isinstance(source, LiveSnapshotSource)
        ):
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "The snapshot source does not match the cockpit mode.",
            )
        static_root = Path(__file__).resolve().parent / "static"
        try:
            assets = {
                "/": (static_root / "index.html").read_bytes(),
                "/assets/app.css": (static_root / "app.css").read_bytes(),
                "/assets/app.js": (static_root / "app.js").read_bytes(),
            }
        except OSError as error:
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "The local cockpit assets are unavailable.",
            ) from error
        object.__setattr__(self, "_config", config)
        object.__setattr__(self, "_source", source)
        object.__setattr__(self, "_static", MappingProxyType(assets))
        object.__setattr__(self, "_sealed", True)

    @property
    def config(self) -> CockpitConfig:
        return self._config

    def static_asset(self, route: str) -> bytes:
        try:
            return bytes(self._static[route])
        except KeyError:
            raise CockpitError(
                "ROUTE_NOT_FOUND",
                "The requested local cockpit route does not exist.",
            ) from None

    def meta_envelope(self) -> dict[str, Any]:
        value = {
            "schema_version": "1.0",
            "cockpit_contract_id": MISSION_CONTRACT_ID,
            "cockpit_contract_hash": MISSION_CONTRACT_HASH,
            "authorization_stage": MISSION_AUTHORIZATION_STAGE,
            "mode": self.config.mode,
            "refresh_seconds": self.config.refresh_seconds,
            "demo_scenario": self.config.demo_scenario,
            "loopback_binding": BIND_ADDRESS,
            "ui_version": UI_VERSION,
            "authorized_read_only_capabilities": dict(_AUTHORIZED_UI_CAPABILITIES),
            "prohibited_capabilities": dict(_PROHIBITED_CAPABILITIES),
            "no_write_declaration": True,
            "no_recalculation_declaration": True,
            "no_network_declaration": True,
            "no_trading_declaration": True,
        }
        return _detached(value)

    def snapshot_envelope(self, scenario: str | None = None) -> dict[str, Any]:
        if self.config.mode == "DEMO":
            selected = scenario or self.config.demo_scenario
            snapshot = self._source.snapshot(selected)
            demo_scenario = selected
        else:
            if scenario is not None:
                raise CockpitError(
                    "DEMO_SCENARIO_INVALID",
                    "Demonstration selection is unavailable in connected mode.",
                )
            snapshot = self._source.snapshot()
            demo_scenario = None
        safe_snapshot = _display_safe(snapshot)
        return _detached(
            {
                "schema_version": "1.0",
                "cockpit_mode": self.config.mode,
                "demo_scenario": demo_scenario,
                "integer_encoding": "DECIMAL_STRING",
                "snapshot": safe_snapshot,
                "snapshot_identity": {
                    "snapshot_id": safe_snapshot["snapshot_id"],
                    "canonical_snapshot_hash": safe_snapshot[
                        "canonical_snapshot_hash"
                    ],
                },
            }
        )


@dataclass
class _SessionState:
    token_digest: bytes
    cookie_digest: bytes | None = None
    consumed: bool = False

    def __post_init__(self) -> None:
        self.lock = threading.Lock()

    @staticmethod
    def _digest(value: str) -> bytes:
        return hashlib.sha256(value.encode("ascii", errors="strict")).digest()

    def consume(self, supplied: str) -> str | None:
        try:
            supplied_digest = self._digest(supplied)
        except (UnicodeEncodeError, AttributeError):
            return None
        with self.lock:
            valid = not self.consumed and hmac.compare_digest(
                supplied_digest, self.token_digest
            )
            if not valid:
                return None
            cookie = secrets.token_urlsafe(32)
            self.cookie_digest = self._digest(cookie)
            self.consumed = True
            return cookie

    def valid_cookie(self, supplied: str) -> bool:
        try:
            supplied_digest = self._digest(supplied)
        except (UnicodeEncodeError, AttributeError):
            return False
        with self.lock:
            expected = self.cookie_digest
            return expected is not None and hmac.compare_digest(
                supplied_digest, expected
            )


class _LoopbackHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class _CockpitHandler(BaseHTTPRequestHandler):
    server_version = "DeltaGridCockpit/0"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        self._handle_read(head=False)

    def do_HEAD(self) -> None:
        self._handle_read(head=True)

    def do_POST(self) -> None:
        self._handle_write()

    def do_PUT(self) -> None:
        self._handle_write()

    def do_PATCH(self) -> None:
        self._handle_write()

    def do_DELETE(self) -> None:
        self._handle_write()

    def do_OPTIONS(self) -> None:
        self._handle_write()

    def do_TRACE(self) -> None:
        self._handle_write()

    def do_CONNECT(self) -> None:
        self._handle_write()

    @property
    def _application(self) -> ResearchCockpitApplication:
        return self.server.application

    @property
    def _session(self) -> _SessionState:
        return self.server.session_state

    def _host_valid(self) -> bool:
        values = self.headers.get_all("Host", failobj=[])
        if len(values) != 1:
            return False
        host = values[0]
        port = self.server.server_address[1]
        return host in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _parsed_target(self) -> tuple[str, Mapping[str, list[str]]] | None:
        target = self.path
        if (
            not isinstance(target, str)
            or not target
            or len(target) > _MAX_REQUEST_TARGET
            or any(ord(character) < 0x20 or ord(character) > 0x7e for character in target)
            or "#" in target
            or re.search(r"%(?![0-9a-fA-F]{2})", target) is not None
        ):
            return None
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
            return None
        try:
            query = parse_qs(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=bool(parsed.query),
                max_num_fields=2,
            )
        except ValueError:
            return None
        return parsed.path, query

    def _has_session(self) -> tuple[bool, str]:
        values = self.headers.get_all("Cookie", failobj=[])
        if not values:
            return False, "SESSION_REQUIRED"
        if len(values) != 1:
            return False, "SESSION_INVALID"
        cookie = SimpleCookie()
        try:
            cookie.load(values[0])
        except CookieError:
            return False, "SESSION_INVALID"
        morsel = cookie.get(_COOKIE_NAME)
        if morsel is None or not self._session.valid_cookie(morsel.value):
            return False, "SESSION_INVALID"
        return True, ""

    def _handle_write(self) -> None:
        if not self._host_valid():
            self._error(HTTPStatus.BAD_REQUEST, "HOST_INVALID")
            return
        if self._parsed_target() is None:
            self._error(HTTPStatus.BAD_REQUEST, "REQUEST_TARGET_INVALID")
            return
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "METHOD_NOT_ALLOWED")

    def _handle_read(self, *, head: bool) -> None:
        if not self._host_valid():
            self._error(HTTPStatus.BAD_REQUEST, "HOST_INVALID", head=head)
            return
        parsed = self._parsed_target()
        if parsed is None:
            self._error(
                HTTPStatus.BAD_REQUEST, "REQUEST_TARGET_INVALID", head=head
            )
            return
        path, query = parsed
        if path.startswith("/session/"):
            if head or query:
                self._error(HTTPStatus.NOT_FOUND, "ROUTE_NOT_FOUND", head=head)
                return
            self._bootstrap(path.removeprefix("/session/"))
            return
        if path not in _NON_SESSION_ROUTES:
            self._error(HTTPStatus.NOT_FOUND, "ROUTE_NOT_FOUND", head=head)
            return
        valid, reason = self._has_session()
        if not valid:
            self._error(HTTPStatus.FORBIDDEN, reason, head=head)
            return
        try:
            if path in self._application._static:
                if query:
                    raise CockpitError(
                        "REQUEST_TARGET_INVALID",
                        "The request target is invalid.",
                    )
                body = self._application.static_asset(path)
            elif path == "/api/v1/meta":
                if query:
                    raise CockpitError(
                        "REQUEST_TARGET_INVALID",
                        "The request target is invalid.",
                    )
                body = self._json_bytes(self._application.meta_envelope())
            else:
                scenario = self._scenario(query)
                body = self._json_bytes(
                    self._application.snapshot_envelope(scenario)
                )
        except CockpitError as error:
            status = (
                HTTPStatus.BAD_REQUEST
                if error.reason_token
                in {"DEMO_SCENARIO_INVALID", "REQUEST_TARGET_INVALID"}
                else HTTPStatus.SERVICE_UNAVAILABLE
            )
            self._error(status, error.reason_token, head=head)
            return
        except Exception:
            self._error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "INTERNAL_COCKPIT_FAILURE",
                head=head,
            )
            return
        self._response(
            HTTPStatus.OK,
            _CONTENT_TYPES[path],
            body,
            head=head,
        )

    def _scenario(self, query: Mapping[str, list[str]]) -> str | None:
        if not query:
            return None
        if set(query) != {"scenario"} or len(query["scenario"]) != 1:
            raise CockpitError(
                "DEMO_SCENARIO_INVALID",
                "The demonstration scenario is invalid.",
            )
        scenario = query["scenario"][0].upper()
        if scenario not in {"HEALTHY", "DEGRADED"}:
            raise CockpitError(
                "DEMO_SCENARIO_INVALID",
                "The demonstration scenario is invalid.",
            )
        return scenario

    def _bootstrap(self, token: str) -> None:
        cookie = self._session.consume(token)
        if cookie is None:
            self._error(
                HTTPStatus.FORBIDDEN,
                "SESSION_BOOTSTRAP_INVALID",
            )
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header(
            "Set-Cookie",
            f"{_COOKIE_NAME}={cookie}; HttpOnly; SameSite=Strict; Path=/",
        )
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    @staticmethod
    def _json_bytes(value: Any) -> bytes:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")

    def _error(
        self,
        status: HTTPStatus,
        reason: str,
        *,
        head: bool = False,
    ) -> None:
        explanations = {
            "SESSION_REQUIRED": "A local cockpit session is required.",
            "SESSION_INVALID": "The local cockpit session is invalid.",
            "SESSION_BOOTSTRAP_INVALID": "The one-time local bootstrap is invalid.",
            "HOST_INVALID": "The request host is not permitted.",
            "METHOD_NOT_ALLOWED": "The HTTP method is not allowed.",
            "ROUTE_NOT_FOUND": "The requested local cockpit route does not exist.",
            "REQUEST_TARGET_INVALID": "The request target is invalid.",
            "DEMO_SCENARIO_INVALID": "The demonstration scenario is invalid.",
            "SNAPSHOT_UNAVAILABLE": "The snapshot is temporarily unavailable.",
            "SNAPSHOT_INTEGRITY_FAILURE": "Snapshot integrity verification failed.",
            "COCKPIT_CONFIGURATION_INVALID": "The cockpit configuration is invalid.",
            "INTERNAL_COCKPIT_FAILURE": "The cockpit could not complete the request.",
        }
        body = self._json_bytes(
            {
                "schema_version": "1.0",
                "error": {
                    "reason_token": reason,
                    "human_explanation": explanations.get(
                        reason, explanations["INTERNAL_COCKPIT_FAILURE"]
                    ),
                },
            }
        )
        self._response(
            status,
            "application/json; charset=utf-8",
            body,
            head=head,
            extra_headers=(
                {"Allow": "GET, HEAD"} if reason == "METHOD_NOT_ALLOWED" else None
            ),
        )

    def _response(
        self,
        status: HTTPStatus,
        content_type: str,
        body: bytes,
        *,
        head: bool,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)


class ResearchCockpitServer:
    """Own one loopback HTTP server and its process-local session lifetime."""

    def __init__(self, application: ResearchCockpitApplication) -> None:
        if not isinstance(application, ResearchCockpitApplication):
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "A validated ResearchCockpitApplication is required.",
            )
        self._application = application
        self._httpd: _LoopbackHTTPServer | None = None
        self._serving = False
        self._closed = False

    @property
    def address(self) -> tuple[str, int] | None:
        if self._httpd is None:
            return None
        return (BIND_ADDRESS, int(self._httpd.server_address[1]))

    def start(self) -> str:
        if self._closed or self._httpd is not None:
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "The cockpit server cannot be started more than once.",
            )
        try:
            httpd = _LoopbackHTTPServer(
                (BIND_ADDRESS, self._application.config.port),
                _CockpitHandler,
            )
        except OSError as error:
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "The loopback HTTP server could not start.",
            ) from error
        token = secrets.token_urlsafe(32)
        httpd.application = self._application
        httpd.session_state = _SessionState(
            token_digest=hashlib.sha256(token.encode("ascii")).digest()
        )
        self._httpd = httpd
        port = int(httpd.server_address[1])
        return f"http://{BIND_ADDRESS}:{port}/session/{token}"

    def serve_forever(self) -> None:
        if self._httpd is None:
            raise CockpitError(
                "COCKPIT_CONFIGURATION_INVALID",
                "The cockpit server must be started before serving.",
            )
        self._serving = True
        try:
            self._httpd.serve_forever(poll_interval=0.1)
        finally:
            self._serving = False

    def shutdown(self) -> None:
        httpd = self._httpd
        if httpd is None or self._closed:
            return
        if self._serving:
            httpd.shutdown()
        httpd.server_close()
        httpd.session_state.token_digest = b""
        httpd.session_state.cookie_digest = None
        self._closed = True

    def __enter__(self) -> ResearchCockpitServer:
        return self

    def __exit__(self, *args: Any) -> None:
        self.shutdown()
