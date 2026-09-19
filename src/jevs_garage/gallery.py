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
from urllib.parse import unquote, urlsplit

from typesafe_sdk import ChoiceAnswer, NoulAnswer, Questions, ScoreAnswer, SystemOneResponse, TypeSafeError

from jevs_garage.operations import OperationRun
from jevs_garage.runtime import JevSignals, PolicyDecision, SignalNames, signals_from_response

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GROUPS = ("critical", "berserk", "fun")


class DemoModule(Protocol):
    """The metadata surface shared by every standalone demo."""

    TITLE: str
    STATE: dict[str, Any]


class SimpleDemoModule(DemoModule, Protocol):
    """Execution surface for a single-stage demo."""

    QUESTIONS: Questions
    SIGNALS: SignalNames

    def evaluate(self) -> SystemOneResponse: ...

    def decide(self, signals: JevSignals) -> PolicyDecision: ...


class StagedDemoModule(DemoModule, Protocol):
    """Execution surface for a multi-stage Berserk demo."""

    QUESTION_SETS: dict[str, Questions]

    def execute(self) -> OperationRun: ...


def discover_demo_paths(root: Path = REPOSITORY_ROOT) -> list[tuple[str, Path]]:
    """Find runnable demo modules in stable group and folder order."""

    demos: list[tuple[str, Path]] = []
    for group in GROUPS:
        group_root = root / group
        if not group_root.is_dir():
            continue
        demo_roots = sorted(path for path in group_root.iterdir() if path.is_dir())
        demos.extend((group, demo_root / "demo.py") for demo_root in demo_roots if (demo_root / "demo.py").is_file())
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


def _question_sets(module: DemoModule) -> dict[str, Questions]:
    staged = getattr(module, "QUESTION_SETS", None)
    if staged is not None:
        return cast(dict[str, Questions], staged)
    simple = cast(SimpleDemoModule, module)
    return {"decision": simple.QUESTIONS}


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


def collect_demos(root: Path = REPOSITORY_ROOT) -> list[dict[str, Any]]:
    """Collect demo metadata without running a model or requiring an API key."""

    demos: list[dict[str, Any]] = []
    for group, path in discover_demo_paths(root):
        module = _load_demo(group, path)
        questions = []
        question_sets = _question_sets(module)
        staged = len(question_sets) > 1
        for stage, stage_questions in question_sets.items():
            for name, question in stage_questions.items():
                if isinstance(question, dict):
                    question_type = question["type"]
                    instructions = question.get("instructions")
                else:
                    question_type = question.type
                    instructions = question.instructions
                label = f"{stage.replace('_', ' ')} / {name.replace('_', ' ')}" if staged else name.replace("_", " ")
                questions.append(
                    {
                        "name": label,
                        "stage": stage,
                        "type": question_type,
                        "instructions": instructions,
                    }
                )
        demos.append(
            {
                "id": f"{group}/{path.parent.name}",
                "group": group,
                "slug": path.parent.name,
                "title": module.TITLE,
                "description": _description(path.with_name("README.md")),
                "state": module.STATE,
                "questions": questions,
                "stage_count": len(question_sets),
                "command": f"uv run python {group}/{path.parent.name}/demo.py",
            }
        )
    return demos


def run_demo(demo_id: str, root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Run one named demo against Jev and apply its deterministic policy."""

    paths = {f"{group}/{path.parent.name}": (group, path) for group, path in discover_demo_paths(root)}
    if demo_id not in paths:
        raise KeyError(demo_id)
    group, path = paths[demo_id]
    module = _load_demo(group, path)
    if hasattr(module, "execute"):
        staged = cast(StagedDemoModule, module)
        operation = staged.execute()
        models = list(dict.fromkeys(stage.response.model for stage in operation.stages))
        signals = [
            _signal_payload(f"{stage.key} / {name}", answer)
            for stage in operation.stages
            for name, answer in stage.response.answers.items()
        ]
        return {
            "model": " -> ".join(models),
            "signals": signals,
            "decision": asdict(operation.decision),
            "controls": list(operation.controls),
            "audit": [asdict(event) for event in operation.audit],
            "correlation_id": operation.correlation_id,
            "policy_version": operation.policy_version,
            "state_fingerprint": operation.state_fingerprint,
        }

    simple = cast(SimpleDemoModule, module)
    response = simple.evaluate()
    decision = simple.decide(signals_from_response(response, simple.SIGNALS))
    return {
        "model": response.model,
        "signals": [_signal_payload(name, answer) for name, answer in response.answers.items()],
        "decision": asdict(decision),
        "controls": [],
        "audit": [],
    }


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
      --berserk: #b56b00;
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
    .demo-card.berserk .stripe { background: var(--berserk); }
    .demo-card.fun .stripe { background: var(--fun); }
    .card-head, .card-body, .card-foot { padding-left: 19px; padding-right: 19px; }
    .card-head { padding-top: 17px; display: flex; justify-content: space-between; gap: 12px; align-items: start; }
    .eyebrow { color: var(--critical); font: 800 11px/1 "DejaVu Sans Mono", monospace; text-transform: uppercase; }
    .berserk .eyebrow { color: var(--berserk); }
    .fun .eyebrow { color: var(--fun); }
    h2 { margin: 8px 0 0; font: 800 20px/1.2 "DejaVu Sans Mono", monospace; letter-spacing: 0; }
    .live-badge { padding: 5px 7px; color: #fff; background: var(--blue); white-space: nowrap; font: 800 11px/1 "DejaVu Sans Mono", monospace; }
    .card-body { padding-top: 13px; color: #494a45; font-size: 13px; line-height: 1.55; }
    .card-foot { padding-top: 15px; padding-bottom: 17px; display: grid; gap: 10px; }
    .meter { height: 8px; border: 1px solid var(--ink); background: #ddd8cc; }
    .meter > span { display: block; height: 100%; background: var(--critical); }
    .berserk .meter > span { background: var(--berserk); }
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
    .run-area { grid-column: 1 / -1; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
    .run-button { padding: 11px 16px; border: 2px solid var(--ink); background: var(--yellow); color: var(--ink); box-shadow: 3px 3px 0 var(--ink); cursor: pointer; font-weight: 800; }
    .run-button:disabled { cursor: wait; opacity: .65; }
    .run-status { margin: 0; color: var(--muted); font: 700 12px/1.4 "DejaVu Sans Mono", monospace; }
    .operation-record { grid-column: 1 / -1; padding: 17px; border: 2px solid var(--ink); background: var(--panel); }
    .operation-record ul { margin: 0; padding-left: 20px; line-height: 1.55; }
    .operation-record pre { max-height: 220px; }
    [hidden] { display: none !important; }
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
    <div class="counter"><span id="count">--</span> BAYS<br>LIVE ON DEMAND</div>
  </header>
  <main>
    <nav class="toolbar" aria-label="Gallery controls">
      <div class="segmented" aria-label="Demo group">
        <button type="button" data-group="all" aria-pressed="true">All bays</button>
        <button type="button" data-group="critical" aria-pressed="false">Critical</button>
        <button type="button" data-group="berserk" aria-pressed="false">Berserk</button>
        <button type="button" data-group="fun" aria-pressed="false">Fun</button>
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
      <section><h3 id="signals-heading" class="section-title">Question contract</h3><div id="detail-signals" class="signal-list"></div></section>
      <section id="detail-policy" class="policy" hidden><h3 class="section-title">Deterministic policy</h3><strong id="detail-action"></strong><p id="detail-reason"></p><p id="detail-meta" class="policy-meta"></p></section>
      <section id="detail-controls" class="operation-record" hidden><h3 class="section-title">Non-negotiable controls</h3><ul id="control-list"></ul></section>
      <section id="detail-audit" class="operation-record" hidden><h3 class="section-title">Operation audit</h3><pre id="audit-log"></pre></section>
      <div class="run-area"><button id="run" class="run-button" type="button">Run Jev</button><p id="run-status" class="run-status">Uses TYPESAFE_API_KEY on this machine.</p></div>
      <div id="detail-command" class="command"></div>
    </div>
  </dialog>
  <script>
    const view = { group: "all", demos: [], current: null };
    const grid = document.querySelector("#grid");
    const status = document.querySelector("#status");
    const detail = document.querySelector("#detail");
    const signals = document.querySelector("#detail-signals");
    const policy = document.querySelector("#detail-policy");
    const controlsPanel = document.querySelector("#detail-controls");
    const auditPanel = document.querySelector("#detail-audit");
    const runButton = document.querySelector("#run");
    const runStatus = document.querySelector("#run-status");

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

    function renderQuestions(questions) {
      signals.replaceChildren();
      questions.forEach((question) => {
        const row = element("div", "signal-row");
        const top = element("div", "signal-top");
        top.append(element("span", "signal-name", question.name), element("span", "signal-type", question.type));
        const instructions = typeof question.instructions === "string" ? question.instructions : JSON.stringify(question.instructions);
        row.append(top, element("div", "signal-value", instructions));
        signals.append(row);
      });
    }

    function renderResult(result) {
      document.querySelector("#signals-heading").textContent = `Typed Jev signals / ${result.model}`;
      signals.replaceChildren();
      result.signals.forEach((signal) => {
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
      document.querySelector("#detail-action").textContent = result.decision.action;
      document.querySelector("#detail-reason").textContent = result.decision.reason;
      document.querySelector("#detail-meta").textContent = `Owner: ${result.decision.owner} | policy confidence: ${percent(result.decision.confidence)}`;
      policy.classList.toggle("fallback", result.decision.fallback);
      policy.hidden = false;
      const controlList = document.querySelector("#control-list");
      controlList.replaceChildren();
      (result.controls || []).forEach((control) => controlList.append(element("li", "", control)));
      controlsPanel.hidden = !result.controls?.length;
      const auditHeader = result.correlation_id
        ? `${result.correlation_id} | policy ${result.policy_version} | state ${result.state_fingerprint}\n`
        : "";
      document.querySelector("#audit-log").textContent = auditHeader + (result.audit || [])
        .map((entry) => `${entry.sequence}. ${entry.event} | ${entry.detail}`).join("\n");
      auditPanel.hidden = !result.audit?.length;
    }

    function openDetail(demo) {
      view.current = demo;
      document.querySelector("#detail-group").textContent = demo.group;
      document.querySelector("#detail-title").textContent = demo.title;
      document.querySelector("#detail-state").textContent = JSON.stringify(demo.state, null, 2);
      document.querySelector("#detail-command").textContent = demo.command;
      document.querySelector("#signals-heading").textContent = "Question contract";
      renderQuestions(demo.questions);
      policy.hidden = true;
      controlsPanel.hidden = true;
      auditPanel.hidden = true;
      runButton.disabled = false;
      runButton.textContent = demo.stage_count > 1 ? `Run ${demo.stage_count} Jev stages` : "Run Jev";
      runStatus.textContent = demo.stage_count > 1
        ? "Runs a staged, live evaluation. No operational credentials are available."
        : "Uses TYPESAFE_API_KEY on this machine.";
      detail.showModal();
    }

    async function runLive() {
      if (!view.current) return;
      runButton.disabled = true;
      runButton.textContent = "Calling Jev...";
      runStatus.textContent = "Waiting for a live TypeSafe response.";
      try {
        const response = await fetch(`/api/demos/${view.current.id}`, { method: "POST" });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        renderResult(payload);
        runStatus.textContent = "Live result received. No side effect was executed.";
        runButton.textContent = "Run again";
      } catch (error) {
        runStatus.textContent = `Live run failed: ${error.message}`;
        runButton.textContent = "Try again";
      } finally {
        runButton.disabled = false;
      }
    }

    function render() {
      const demos = view.demos.filter((demo) => view.group === "all" || demo.group === view.group);
      grid.replaceChildren();
      document.querySelector("#count").textContent = String(view.demos.length).padStart(2, "0");
      status.textContent = `${demos.length} ${view.group === "all" ? "open" : view.group} bays | live calls run on demand`;
      if (!demos.length) grid.append(element("p", "empty", "No bays match this filter."));
      demos.forEach((demo) => {
        const card = element("button", `demo-card ${demo.group}`);
        card.type = "button";
        card.setAttribute("aria-label", `Open ${demo.title}`);
        const stripe = element("span", "stripe");
        const head = element("div", "card-head");
        const titleWrap = element("div");
        titleWrap.append(element("span", "eyebrow", demo.group), element("h2", "", demo.title));
        head.append(titleWrap, element("span", "live-badge", demo.stage_count > 1 ? `${demo.stage_count} STAGES` : "LIVE"));
        const body = element("div", "card-body", demo.description);
        const foot = element("div", "card-foot");
        foot.append(element("div", "outcome", "OPEN BAY >"));
        card.append(stripe, head, body, foot);
        card.addEventListener("click", () => openDetail(demo));
        grid.append(card);
      });
    }

    async function load() {
      status.textContent = "Loading demo contracts...";
      try {
        const response = await fetch("/api/demos");
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
    runButton.addEventListener("click", runLive);
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
            root = cast(GalleryServer, self.server).gallery_root
            body = json.dumps(collect_demos(root), ensure_ascii=False).encode()
            self._write(HTTPStatus.OK, body, "application/json")
            return
        self._write(HTTPStatus.NOT_FOUND, b'{"error":"not found"}', "application/json")

    def do_POST(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        prefix = "/api/demos/"
        if not request.path.startswith(prefix):
            self._write(HTTPStatus.NOT_FOUND, b'{"error":"not found"}', "application/json")
            return

        demo_id = unquote(request.path.removeprefix(prefix)).strip("/")
        root = cast(GalleryServer, self.server).gallery_root
        try:
            payload = run_demo(demo_id, root)
        except KeyError:
            self._write(HTTPStatus.NOT_FOUND, b'{"error":"unknown demo"}', "application/json")
            return
        except SystemExit as error:
            body = json.dumps({"error": str(error)}).encode()
            self._write(HTTPStatus.SERVICE_UNAVAILABLE, body, "application/json")
            return
        except TypeSafeError as error:
            body = json.dumps({"error": f"TypeSafe API call failed: {error}"}).encode()
            self._write(HTTPStatus.BAD_GATEWAY, body, "application/json")
            return

        body = json.dumps(payload, ensure_ascii=False).encode()
        self._write(HTTPStatus.OK, body, "application/json")

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
