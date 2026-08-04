"""Command-line entry point for the loopback-only Mission 96B cockpit."""

from __future__ import annotations

import argparse
import sys
import webbrowser

from .models import CockpitConfig, CockpitError
from .server import ResearchCockpitApplication, ResearchCockpitServer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("demo", "connected"), default="demo")
    parser.add_argument(
        "--demo-scenario",
        choices=("healthy", "degraded"),
        default="healthy",
    )
    parser.add_argument("--ledger")
    parser.add_argument("--result-root")
    parser.add_argument("--repository-root")
    parser.add_argument("--expected-repository-commit")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--refresh-seconds", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    selected_argv = sys.argv[1:] if argv is None else argv
    arguments = parser.parse_args(selected_argv)
    connected = arguments.mode == "connected"
    if connected and any(
        item == "--demo-scenario" or item.startswith("--demo-scenario=")
        for item in selected_argv
    ):
        parser.error("--demo-scenario is valid only in demo mode")
    try:
        config = CockpitConfig(
            mode=arguments.mode,
            demo_scenario=None if connected else arguments.demo_scenario,
            ledger_path=arguments.ledger,
            result_root_path=arguments.result_root,
            repository_root_path=arguments.repository_root,
            expected_repository_commit=arguments.expected_repository_commit,
            port=arguments.port,
            refresh_seconds=arguments.refresh_seconds,
            open_browser=arguments.open_browser,
        )
        application = ResearchCockpitApplication(config)
        with ResearchCockpitServer(application) as server:
            bootstrap_url = server.start()
            print(bootstrap_url, flush=True)
            if config.open_browser:
                webbrowser.open(bootstrap_url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    except CockpitError as error:
        parser.error(error.human_explanation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
