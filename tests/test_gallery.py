from __future__ import annotations

import json
import threading
from copy import deepcopy
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from jevs_garage.gallery import INDEX_HTML, collect_demos, create_server, validate_demo_state


def test_gallery_discovers_every_demo() -> None:
    demos = collect_demos()
    groups = [demo["group"] for demo in demos]

    assert len(demos) == 23
    assert groups.count("critical") == 12
    assert groups.count("berserk") == 1
    assert groups.count("fun") == 10
    assert sorted(len(demo["questions"]) for demo in demos).count(6) == 1
    assert sorted(len(demo["questions"]) for demo in demos).count(3) == 22
    assert all("signals" not in demo and "decision" not in demo for demo in demos)


def test_gallery_shell_and_api_are_served() -> None:
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]

    try:
        with urlopen(f"http://{host}:{port}/", timeout=2) as response:  # noqa: S310
            html = response.read().decode()
        with urlopen(f"http://{host}:{port}/api/demos", timeout=2) as response:  # noqa: S310
            demos = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert html == INDEX_HTML
    assert "Jev's Garage" in html
    assert len(demos) == 23
    assert "Berserk" in html
    assert demos[0]["questions"][0]["type"] in {"choice", "score", "noul"}


def test_edited_values_preserve_the_input_contract() -> None:
    demo = next(item for item in collect_demos() if item["id"] == "critical/fraud-screening")
    state = deepcopy(demo["state"])
    state["amount_usd"] = 72.45
    state["device"]["trusted"] = True
    state["signals"].append("unfamiliar merchant")

    assert validate_demo_state(demo["id"], state) == []


def test_input_contract_reports_precise_shape_errors() -> None:
    demo = next(item for item in collect_demos() if item["id"] == "critical/fraud-screening")
    state = deepcopy(demo["state"])
    del state["device"]["account_age_days"]
    state["amount_usd"] = "expensive"
    state["unexpected"] = True

    errors = validate_demo_state(demo["id"], state)

    assert "$.device.account_age_days: required field is missing" in errors
    assert "$.amount_usd: expected float, got str" in errors
    assert "$.unexpected: unknown field" in errors


def test_validation_endpoint_checks_json_before_any_live_call() -> None:
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    demo = next(item for item in collect_demos() if item["id"] == "critical/fraud-screening")
    url = f"http://{host}:{port}/api/demos/{demo['id']}/validate"

    try:
        valid_request = Request(
            url,
            data=json.dumps({"state": demo["state"]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(valid_request, timeout=2) as response:  # noqa: S310
            valid = json.loads(response.read())

        invalid_state = deepcopy(demo["state"])
        del invalid_state["merchant"]
        invalid_request = Request(
            url,
            data=json.dumps({"state": invalid_state}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(invalid_request, timeout=2) as response:  # noqa: S310
            invalid = json.loads(response.read())

        malformed_request = Request(
            url,
            data=b"{",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as malformed:
            urlopen(malformed_request, timeout=2)  # noqa: S310
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert valid["valid"] is True
    assert valid["errors"] == []
    assert valid["bytes"] > 0
    assert invalid["valid"] is False
    assert "$.merchant: required field is missing" in invalid["errors"]
    assert malformed.value.code == 400


def test_gallery_uses_certainty_driven_colors() -> None:
    assert "function confidenceColor(value)" in INDEX_HTML
    assert "fill.style.backgroundColor = confidenceColor(signal.certainty)" in INDEX_HTML


def test_gallery_highlights_json_without_injecting_html() -> None:
    assert "function renderJsonHighlight()" in INDEX_HTML
    assert 'document.createElement("span")' in INDEX_HTML
    assert "token.textContent = match[0]" in INDEX_HTML
    assert "inputHighlight.replaceChildren(fragment)" in INDEX_HTML
    assert "innerHTML" not in INDEX_HTML
