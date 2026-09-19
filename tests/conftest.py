from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--live", action="store_true", help="Run tests that call the TypeSafe API.")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    live_requested = config.getoption("--live")
    if live_requested:
        load_dotenv()
        if not os.getenv("TYPESAFE_API_KEY"):
            raise pytest.UsageError("--live requires TYPESAFE_API_KEY in the environment or .env")
        skip = pytest.mark.skip(reason="excluded from the live-only test run")
        for item in items:
            if "live" not in item.keywords:
                item.add_marker(skip)
        return

    skip = pytest.mark.skip(reason="requires --live and TYPESAFE_API_KEY")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
