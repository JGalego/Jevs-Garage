from __future__ import annotations

import json
import threading
from urllib.request import urlopen

from jevs_garage.gallery import INDEX_HTML, collect_demos, create_server


def test_gallery_discovers_every_demo() -> None:
    demos = collect_demos()
    groups = [demo["group"] for demo in demos]

    assert len(demos) == 22
    assert groups.count("critical") == 12
    assert groups.count("fun") == 10
    assert all(len(demo["questions"]) == 3 for demo in demos)
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
    assert len(demos) == 22
    assert demos[0]["questions"][0]["type"] in {"choice", "score", "noul"}
