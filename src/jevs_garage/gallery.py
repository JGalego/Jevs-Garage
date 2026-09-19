"""Local web gallery for browsing every Jev's Garage demo."""

# ruff: noqa: E501 -- keeping embedded HTML, CSS, and JavaScript readable is clearer than Python wrapping.

from __future__ import annotations

import argparse
import errno
import importlib.util
import json
import sys
import threading
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

from typesafe_sdk import ChoiceAnswer, NoulAnswer, ScoreAnswer, SystemOneResponse

from jevs_garage.runtime import PolicyDecision

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GROUPS = ("critical", "fun")
SCENARIOS = ("confident", "uncertain")


class DemoModule(Protocol):
    """The small public surface shared by every standalone demo."""

    TITLE: str
    STATE: dict[str, Any]

    def evaluate(self, *, live: bool = False, scenario: str = "confident") -> SystemOneResponse: ...

    def decide(self, response: SystemOneResponse) -> PolicyDecision: ...


def discover_demo_paths(root: Path = REPOSITORY_ROOT) -> list[tuple[str, Path]]:
    """Find runnable demo modules in stable group and folder order."""

    demos: list[tuple[str, Path]] = []
    for group in GROUPS:
        group_root = root / group
        if not group_root.is_dir():
            continue
        for demo_root in sorted(path for path in group_root.iterdir() if path.is_dir()):
            demo_path = demo_root / "demo.py"
            if demo_path.is_file() and (demo_root / "fixtures.json").is_file():
                demos.append((group, demo_path))
    return demos


def _load_demo(group: str, path: Path) -> DemoModule:
    module_name = f"garage_gallery_{group}_{path.parent.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load demo module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return cast(DemoModule, cast(ModuleType, module))


def _description(path: Path) -> str:
    sections = path.read_text(encoding="utf-8").split("\n\n")
    return " ".join(sections[1].splitlines()) if len(sections) > 1 else ""


def _signal_payload(name: str, answer: ChoiceAnswer | ScoreAnswer | NoulAnswer) -> dict[str, Any]:
    if isinstance(answer, ChoiceAnswer):
        value = answer.choice
        certainty = answer.confidence
        probabilities = answer.probabilities
    elif isinstance(answer, ScoreAnswer):
        nearest = min(answer.legend, key=lambda point: abs(point - answer.score))
        value = f"{answer.score:.1f} / {answer.legend[nearest]}"
        certainty = answer.confidence
        probabilities = {str(point): probability for point, probability in answer.probabilities.items()}
    else:
        value = f"{'yes' if answer.noul >= 0.5 else 'no'} / {answer.noul:.0%} yes"
        certainty = abs(answer.noul - 0.5) * 2
        probabilities = {"no": 1 - answer.noul, "yes": answer.noul}
    return {
        "name": name.replace("_", " "),
        "type": answer.type,
        "value": value,
        "certainty": certainty,
        "probabilities": probabilities,
    }


def collect_demos(scenario: str = "confident", root: Path = REPOSITORY_ROOT) -> list[dict[str, Any]]:
    """Evaluate every demo against one offline fixture scenario for the web UI."""

    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario {scenario!r}")

    demos: list[dict[str, Any]] = []
    for group, path in discover_demo_paths(root):
        module = _load_demo(group, path)
        response = module.evaluate(scenario=scenario)
        decision = module.decide(response)
        demos.append(
            {
                "id": f"{group}/{path.parent.name}",
                "group": group,
                "slug": path.parent.name,
                "title": module.TITLE,
                "description": _description(path.with_name("README.md")),
                "state": module.STATE,
                "model": response.model,
                "signals": [_signal_payload(name, answer) for name, answer in response.answers.items()],
                "decision": asdict(decision),
                "command": f"uv run python {group}/{path.parent.name}/demo.py",
            }
        )
    return demos


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Jev's Garage</title>
  <style>
    :root {
      --ink: #171916;
      --paper: #f4f1e9;
      --panel: #fffdf8;
      --line: #c8c3b7;
      --muted: #68675f;
      --critical: #ce4538;
      --fun: #17836a;
      --yellow: #f3c447;
      --blue: #3674bb;
      --shadow: 5px 5px 0 #171916;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background-color: var(--paper);
      background-image:
        linear-gradient(rgba(23, 25, 22, .055) 1px, transparent 1px),
        linear-gradient(90deg, rgba(23, 25, 22, .055) 1px, transparent 1px);
      background-size: 24px 24px;
      font-family: "DejaVu Sans", sans-serif;
      min-height: 100vh;
    }
    button { font: inherit; }
    .topbar {
      min-height: 116px;
      padding: 24px clamp(18px, 4vw, 58px);
      color: #fff;
      background: var(--ink);
      border-bottom: 8px solid var(--yellow);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
    }
    .brand { display: flex; align-items: center; gap: 17px; }
    .brand-mark {
      width: 58px;
      height: 58px;
      display: grid;
      place-items: center;
      border: 3px solid var(--yellow);
      color: var(--yellow);
      font: 800 21px/1 "DejaVu Sans Mono", monospace;
      transform: rotate(-2deg);
    }
    h1 { margin: 0; font: 800 clamp(25px, 4vw, 40px)/1 "DejaVu Sans Mono", monospace; letter-spacing: 0; }
    .subtitle { margin: 8px 0 0; color: #c9c8c1; font-size: 14px; }
    .counter { text-align: right; font: 700 14px/1.45 "DejaVu Sans Mono", monospace; color: var(--yellow); }
    main { width: min(1440px, 100%); margin: 0 auto; padding: 28px clamp(18px, 4vw, 58px) 64px; }
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 18px;
      margin-bottom: 26px;
      padding: 12px;
      background: var(--panel);
      border: 2px solid var(--ink);
      box-shadow: 3px 3px 0 var(--ink);
    }
    .segmented { display: flex; gap: 5px; flex-wrap: wrap; }
    .segmented button {
      min-height: 38px;
      padding: 7px 13px;
      border: 2px solid transparent;
      background: transparent;
      color: var(--ink);
      cursor: pointer;
      font-weight: 800;
    }
    .segmented button[aria-pressed="true"] { border-color: var(--ink); background: var(--yellow); }
    .scenario button[aria-pressed="true"] { background: var(--blue); color: #fff; }
    .status { min-height: 22px; margin: 0 0 14px; color: var(--muted); font: 700 13px/1.4 "DejaVu Sans Mono", monospace; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 310px), 1fr)); gap: 19px; }
    .demo-card {
      min-height: 252px;
      padding: 0;
      text-align: left;
      color: var(--ink);
      background: var(--panel);
      border: 2px solid var(--ink);
      box-shadow: var(--shadow);
      cursor: pointer;
      display: grid;
      grid-template-rows: 8px auto 1fr auto;
      overflow: hidden;
      transition: transform 130ms ease, box-shadow 130ms ease;
    }
    .demo-card:hover, .demo-card:focus-visible { transform: translate(-2px, -2px); box-shadow: 8px 8px 0 var(--ink); outline: none; }
    .stripe { background: var(--critical); }
    .demo-card.fun .stripe { background: var(--fun); }
    .card-head, .card-body, .card-foot { padding-left: 19px; padding-right: 19px; }
    .card-head { padding-top: 17px; display: flex; justify-content: space-between; gap: 12px; align-items: start; }
    .eyebrow { color: var(--critical); font: 800 11px/1 "DejaVu Sans Mono", monospace; text-transform: uppercase; }
    .fun .eyebrow { color: var(--fun); }
    h2 { margin: 8px 0 0; font: 800 20px/1.2 "DejaVu Sans Mono", monospace; letter-spacing: 0; }
    .confidence { white-space: nowrap; font: 800 12px/1 "DejaVu Sans Mono", monospace; }
    .card-body { padding-top: 13px; color: #494a45; font-size: 13px; line-height: 1.55; }
    .card-foot { padding-top: 15px; padding-bottom: 17px; display: grid; gap: 10px; }
    .meter { height: 8px; border: 1px solid var(--ink); background: #ddd8cc; }
    .meter > span { display: block; height: 100%; background: var(--critical); }
    .fun .meter > span { background: var(--fun); }
    .outcome { font: 700 12px/1.35 "DejaVu Sans Mono", monospace; }
    .outcome.fallback { color: #8b5c00; }
    dialog {
      width: min(920px, calc(100vw - 32px));
      max-height: calc(100vh - 32px);
      padding: 0;
      color: var(--ink);
      background: var(--paper);
      border: 3px solid var(--ink);
      box-shadow: 10px 10px 0 rgba(0, 0, 0, .35);
    }
    dialog::backdrop { background: rgba(18, 20, 18, .76); }
    .dialog-head { padding: 21px 24px; background: var(--ink); color: #fff; display: flex; justify-content: space-between; gap: 18px; }
    .dialog-head h2 { margin: 4px 0 0; }
    .close {
      width: 38px; height: 38px; border: 2px solid #fff; background: transparent; color: #fff;
      cursor: pointer; font-size: 25px; line-height: 1;
    }
    .detail { padding: 24px; display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, .85fr); gap: 24px; }
    .section-title { margin: 0 0 10px; font: 800 12px/1 "DejaVu Sans Mono", monospace; text-transform: uppercase; color: var(--muted); }
    pre { margin: 0; max-height: 310px; overflow: auto; padding: 16px; background: #272a26; color: #f7f2e8; font: 12px/1.55 "DejaVu Sans Mono", monospace; }
    .signal-list { display: grid; gap: 15px; }
    .signal-row { border-bottom: 1px solid var(--line); padding-bottom: 12px; }
    .signal-top { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
    .signal-name { font-weight: 800; text-transform: capitalize; }
    .signal-type { color: var(--blue); font: 700 11px/1 "DejaVu Sans Mono", monospace; text-transform: uppercase; }
    .signal-value { margin: 6px 0 7px; font: 700 13px/1.3 "DejaVu Sans Mono", monospace; }
    .policy { grid-column: 1 / -1; padding: 18px; border: 2px solid var(--fun); background: var(--panel); }
    .policy.fallback { border-color: #aa7200; }
    .policy strong { display: block; margin-bottom: 7px; font: 800 16px/1.35 "DejaVu Sans Mono", monospace; }
    .policy p { margin: 5px 0; line-height: 1.5; }
    .policy-meta { color: var(--muted); font-size: 12px; }
    .command { grid-column: 1 / -1; padding: 12px 14px; background: #ded9cc; font: 12px/1.4 "DejaVu Sans Mono", monospace; overflow-x: auto; }
    .empty { padding: 48px 0; color: var(--muted); font-weight: 700; }
    @media (max-width: 720px) {
      .topbar { align-items: flex-start; }
      .counter { display: none; }
      .toolbar { align-items: stretch; flex-direction: column; }
      .detail { grid-template-columns: 1fr; }
      .policy, .command { grid-column: 1; }
    }
    @media (prefers-reduced-motion: reduce) { .demo-card { transition: none; } }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">JG</div>
      <div><h1>Jev's Garage</h1><p class="subtitle">Typed decisions, deterministic guardrails, small useful machines.</p></div>
    </div>
    <div class="counter"><span id="count">--</span> BAYS<br>OFFLINE FIXTURES</div>
  </header>
  <main>
    <nav class="toolbar" aria-label="Gallery controls">
      <div class="segmented" aria-label="Demo group">
        <button type="button" data-group="all" aria-pressed="true">All bays</button>
        <button type="button" data-group="critical" aria-pressed="false">Critical</button>
        <button type="button" data-group="fun" aria-pressed="false">Fun</button>
      </div>
      <div class="segmented scenario" aria-label="Fixture scenario">
        <button type="button" data-scenario="confident" aria-pressed="true">Confident</button>
        <button type="button" data-scenario="uncertain" aria-pressed="false">Uncertain</button>
      </div>
    </nav>
    <p id="status" class="status" role="status">Opening the bay doors...</p>
    <section id="grid" class="grid" aria-label="Demo gallery"></section>
  </main>
  <dialog id="detail">
    <div class="dialog-head">
      <div><span id="detail-group" class="eyebrow"></span><h2 id="detail-title"></h2></div>
      <button id="close" class="close" type="button" aria-label="Close details" title="Close">&times;</button>
    </div>
    <div class="detail">
      <section><h3 class="section-title">Sample state</h3><pre id="detail-state"></pre></section>
      <section><h3 class="section-title">Typed Jev signals</h3><div id="detail-signals" class="signal-list"></div></section>
      <section id="detail-policy" class="policy"><h3 class="section-title">Deterministic policy</h3><strong id="detail-action"></strong><p id="detail-reason"></p><p id="detail-meta" class="policy-meta"></p></section>
      <div id="detail-command" class="command"></div>
    </div>
  </dialog>
  <script>
    const view = { group: "all", scenario: "confident", demos: [] };
    const grid = document.querySelector("#grid");
    const status = document.querySelector("#status");
    const detail = document.querySelector("#detail");

    function element(tag, className, text) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }

    function percent(value) { return `${Math.round(value * 100)}%`; }

    function setPressed(selector, attribute, value) {
      document.querySelectorAll(selector).forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset[attribute] === value));
      });
    }

    function openDetail(demo) {
      document.querySelector("#detail-group").textContent = demo.group;
      document.querySelector("#detail-title").textContent = demo.title;
      document.querySelector("#detail-state").textContent = JSON.stringify(demo.state, null, 2);
      document.querySelector("#detail-command").textContent = demo.command;
      document.querySelector("#detail-action").textContent = demo.decision.action;
      document.querySelector("#detail-reason").textContent = demo.decision.reason;
      document.querySelector("#detail-meta").textContent = `Owner: ${demo.decision.owner} | policy confidence: ${percent(demo.decision.confidence)}`;
      document.querySelector("#detail-policy").classList.toggle("fallback", demo.decision.fallback);
      const signals = document.querySelector("#detail-signals");
      signals.replaceChildren();
      demo.signals.forEach((signal) => {
        const row = element("div", "signal-row");
        const top = element("div", "signal-top");
        top.append(element("span", "signal-name", signal.name), element("span", "signal-type", signal.type));
        const meter = element("div", "meter");
        const fill = element("span");
        fill.style.width = percent(signal.certainty);
        meter.append(fill);
        row.append(top, element("div", "signal-value", signal.value), meter);
        signals.append(row);
      });
      detail.showModal();
    }

    function render() {
      const demos = view.demos.filter((demo) => view.group === "all" || demo.group === view.group);
      grid.replaceChildren();
      document.querySelector("#count").textContent = String(view.demos.length).padStart(2, "0");
      status.textContent = `${demos.length} ${view.group === "all" ? "open" : view.group} bays | ${view.scenario} fixture`;
      if (!demos.length) grid.append(element("p", "empty", "No bays match this filter."));
      demos.forEach((demo) => {
        const card = element("button", `demo-card ${demo.group}`);
        card.type = "button";
        card.setAttribute("aria-label", `Open ${demo.title}`);
        const stripe = element("span", "stripe");
        const head = element("div", "card-head");
        const titleWrap = element("div");
        titleWrap.append(element("span", "eyebrow", demo.group), element("h2", "", demo.title));
        head.append(titleWrap, element("span", "confidence", percent(demo.decision.confidence)));
        const body = element("div", "card-body", demo.description);
        const foot = element("div", "card-foot");
        const meter = element("div", "meter");
        const fill = element("span");
        fill.style.width = percent(demo.decision.confidence);
        meter.append(fill);
        const outcome = element("div", `outcome${demo.decision.fallback ? " fallback" : ""}`, demo.decision.fallback ? "SAFE FALLBACK" : demo.decision.action);
        foot.append(meter, outcome);
        card.append(stripe, head, body, foot);
        card.addEventListener("click", () => openDetail(demo));
        grid.append(card);
      });
    }

    async function load() {
      status.textContent = "Loading offline fixtures...";
      try {
        const response = await fetch(`/api/demos?scenario=${view.scenario}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        view.demos = await response.json();
        render();
      } catch (error) {
        status.textContent = `Could not load the gallery: ${error.message}`;
      }
    }

    document.querySelectorAll("[data-group]").forEach((button) => button.addEventListener("click", () => {
      view.group = button.dataset.group;
      setPressed("[data-group]", "group", view.group);
      render();
    }));
    document.querySelectorAll("[data-scenario]").forEach((button) => button.addEventListener("click", () => {
      view.scenario = button.dataset.scenario;
      setPressed("[data-scenario]", "scenario", view.scenario);
      load();
    }));
    document.querySelector("#close").addEventListener("click", () => detail.close());
    detail.addEventListener("click", (event) => { if (event.target === detail) detail.close(); });
    load();
  </script>
</body>
</html>
"""


class GalleryServer(ThreadingHTTPServer):
    """HTTP server carrying the repository root used by its request handlers."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], root: Path) -> None:
        self.gallery_root = root
        super().__init__(address, GalleryHandler)


class GalleryHandler(BaseHTTPRequestHandler):
    """Serve the gallery shell, health check, and offline demo data."""

    server_version = "JevsGarage/1.0"

    def _write(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self';",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        if request.path == "/":
            self._write(HTTPStatus.OK, INDEX_HTML.encode(), "text/html; charset=utf-8")
            return
        if request.path == "/healthz":
            self._write(HTTPStatus.OK, b'{"status":"ok"}', "application/json")
            return
        if request.path == "/api/demos":
            scenario = parse_qs(request.query).get("scenario", ["confident"])[0]
            try:
                root = cast(GalleryServer, self.server).gallery_root
                body = json.dumps(collect_demos(scenario, root), ensure_ascii=False).encode()
            except ValueError as error:
                body = json.dumps({"error": str(error)}).encode()
                self._write(HTTPStatus.BAD_REQUEST, body, "application/json")
                return
            self._write(HTTPStatus.OK, body, "application/json")
            return
        self._write(HTTPStatus.NOT_FOUND, b'{"error":"not found"}', "application/json")

    def log_message(self, format: str, *args: object) -> None:
        return


def create_server(host: str, port: int, root: Path = REPOSITORY_ROOT) -> GalleryServer:
    """Bind the requested port, moving upward when the default is occupied."""

    candidates = (0,) if port == 0 else range(port, port + 10)
    last_error: OSError | None = None
    for candidate in candidates:
        try:
            return GalleryServer((host, candidate), root)
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            last_error = error
    raise RuntimeError(f"Could not find an open port from {port} to {port + 9}") from last_error


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse every Jev's Garage demo in a local web gallery.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = create_server(args.host, args.port)
    bound_host, bound_port = server.server_address[:2]
    browser_host = "127.0.0.1" if bound_host in {"0.0.0.0", "::"} else bound_host
    url = f"http://{browser_host}:{bound_port}"
    print(f"Jev's Garage is open at {url}", flush=True)
    print("Press Ctrl+C to close the doors.", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
