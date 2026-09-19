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
from collections.abc import Callable, Mapping
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from types import ModuleType
from typing import Any, Protocol, cast
from urllib.parse import unquote, urlsplit

from typesafe_sdk import (
    ChoiceAnswer,
    NoulAnswer,
    Question,
    Questions,
    ScoreAnswer,
    SystemOneResponse,
    TypeSafeClient,
    TypeSafeError,
)

from jevs_garage.operations import OperationRun, ProgressCallback, ProgressEvent, report_progress
from jevs_garage.runtime import JevSignals, PolicyDecision, SignalNames, require_live_api_key, signals_from_response

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GROUPS = ("critical", "berserk", "fun")
MAX_INPUT_BYTES = 128_000


class InputPayloadError(ValueError):
    """A client input error carrying its HTTP response status."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


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

    def execute(
        self,
        state: dict[str, Any] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> OperationRun: ...


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


def _progress_steps(module: DemoModule, question_sets: dict[str, Questions]) -> list[dict[str, str]]:
    configured = getattr(module, "PROGRESS_STEPS", None)
    if configured is not None:
        return [{"key": key, "label": label} for key, label in configured]
    steps = [{"key": key, "label": key.replace("_", " ").title()} for key in question_sets]
    steps.append({"key": "policy", "label": "Deterministic policy"})
    return steps


def _same_json_type(value: Any, template: Any) -> bool:
    if isinstance(template, bool):
        return isinstance(value, bool)
    if isinstance(template, int | float):
        return isinstance(value, int | float) and not isinstance(value, bool)
    return type(value) is type(template)


def _validate_shape(value: Any, template: Any, path: str, errors: list[str]) -> None:
    if not _same_json_type(value, template):
        errors.append(f"{path}: expected {type(template).__name__}, got {type(value).__name__}")
        return
    if isinstance(template, dict):
        value_keys = set(value)
        template_keys = set(template)
        for key in sorted(template_keys - value_keys):
            errors.append(f"{path}.{key}: required field is missing")
        for key in sorted(value_keys - template_keys):
            errors.append(f"{path}.{key}: unknown field")
        for key in sorted(template_keys & value_keys):
            _validate_shape(value[key], template[key], f"{path}.{key}", errors)
    elif isinstance(template, list):
        if template and value:
            if len(template) == len(value):
                for index, (item, exemplar) in enumerate(zip(value, template, strict=True)):
                    _validate_shape(item, exemplar, f"{path}[{index}]", errors)
            elif all(_same_json_type(item, template[0]) for item in template):
                for index, item in enumerate(value):
                    _validate_shape(item, template[0], f"{path}[{index}]", errors)
            else:
                errors.append(f"{path}: expected {len(template)} heterogeneous items, got {len(value)}")


def validate_demo_state(demo_id: str, state: Any, root: Path = REPOSITORY_ROOT) -> list[str]:
    """Validate edited JSON against a demo's canonical state shape."""

    paths = {f"{group}/{path.parent.name}": (group, path) for group, path in discover_demo_paths(root)}
    if demo_id not in paths:
        raise KeyError(demo_id)
    group, path = paths[demo_id]
    module = _load_demo(group, path)
    errors: list[str] = []
    _validate_shape(state, module.STATE, "$", errors)
    semantic_validator = getattr(module, "validate_state", None)
    if not errors and callable(semantic_validator):
        validator = cast(Callable[[dict[str, Any]], list[str]], semantic_validator)
        errors.extend(validator(state))
    return errors


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
                "progress_steps": _progress_steps(module, question_sets),
                "command": f"uv run python {group}/{path.parent.name}/demo.py",
            }
        )
    return demos


def run_demo(
    demo_id: str,
    state: dict[str, Any],
    root: Path = REPOSITORY_ROOT,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run one named demo against Jev and apply its deterministic policy."""

    paths = {f"{group}/{path.parent.name}": (group, path) for group, path in discover_demo_paths(root)}
    if demo_id not in paths:
        raise KeyError(demo_id)
    errors = validate_demo_state(demo_id, state, root)
    if errors:
        raise ValueError("; ".join(errors))
    group, path = paths[demo_id]
    module = _load_demo(group, path)
    if hasattr(module, "execute"):
        staged = cast(StagedDemoModule, module)
        operation = staged.execute(state, on_progress)
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
            "sources": [asdict(source) for source in operation.sources],
            "visualizations": [asdict(visual) for visual in operation.visualizations],
        }

    simple = cast(SimpleDemoModule, module)
    require_live_api_key()
    report_progress(on_progress, "decision", "Jev decision", "running")
    with TypeSafeClient(timeout=30) as client:
        questions = cast(Mapping[str, Question], simple.QUESTIONS)
        response = client.system_one(state=state, questions=questions)
    report_progress(on_progress, "decision", "Jev decision", "completed", f"model={response.model}")
    report_progress(on_progress, "policy", "Deterministic policy", "running")
    decision = simple.decide(signals_from_response(response, simple.SIGNALS))
    report_progress(on_progress, "policy", "Deterministic policy", "completed", f"fallback={decision.fallback}")
    return {
        "model": response.model,
        "signals": [_signal_payload(name, answer) for name, answer in response.answers.items()],
        "decision": asdict(decision),
        "controls": [],
        "audit": [],
        "sources": [],
        "visualizations": [],
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
    .meter > span { display: block; height: 100%; background: var(--blue); transition: width 220ms ease, background-color 220ms ease; }
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
      overflow: hidden;
    }
    dialog::backdrop { background: rgba(18, 20, 18, .76); }
    .dialog-head { padding: 21px 24px; background: var(--ink); color: #fff; display: flex; justify-content: space-between; gap: 18px; }
    .dialog-head h2 { margin: 4px 0 0; }
    .close {
      width: 38px; height: 38px; border: 2px solid #fff; background: transparent; color: #fff;
      cursor: pointer; font-size: 25px; line-height: 1;
    }
    .detail { max-height: calc(100vh - 258px); padding: 24px; overflow: auto; }
    .detail-tabs { display: flex; gap: 0; padding: 0 24px; border-bottom: 2px solid var(--ink); background: var(--panel); overflow-x: auto; }
    .detail-tab { flex: 0 0 auto; min-height: 42px; padding: 9px 15px; border: 0; border-left: 1px solid var(--line); background: transparent; color: var(--muted); cursor: pointer; font-weight: 800; }
    .detail-tab:last-child { border-right: 1px solid var(--line); }
    .detail-tab[aria-selected="true"] { color: var(--ink); background: var(--yellow); }
    .detail-tab:disabled { cursor: not-allowed; opacity: .42; }
    .tab-panel { min-width: 0; }
    .tab-panel[hidden] { display: none; }
    .input-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, .8fr); gap: 24px; }
    .results-layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; }
    .section-title { margin: 0 0 10px; font: 800 12px/1 "DejaVu Sans Mono", monospace; text-transform: uppercase; color: var(--muted); }
    pre { margin: 0; max-height: 310px; overflow: auto; padding: 16px; background: #272a26; color: #f7f2e8; font: 12px/1.55 "DejaVu Sans Mono", monospace; }
    .editor-shell { display: grid; min-width: 0; }
    .input-editor, .input-highlight { grid-area: 1 / 1; width: 100%; min-height: 390px; margin: 0; padding: 16px; border: 2px solid var(--ink); border-radius: 0; font: 12px/1.55 "DejaVu Sans Mono", monospace; tab-size: 2; white-space: pre; overflow-wrap: normal; overflow: auto; }
    .input-highlight { pointer-events: none; background: #272a26; color: #f7f2e8; scrollbar-width: none; }
    .input-highlight::-webkit-scrollbar { display: none; }
    .input-editor { z-index: 1; resize: vertical; background: transparent; color: transparent; caret-color: var(--yellow); -webkit-text-fill-color: transparent; }
    .input-editor::selection { background: rgba(54, 116, 187, .42); }
    .input-editor:focus { outline: 3px solid var(--blue); outline-offset: 2px; }
    .json-key { color: #7fc7ff; }
    .json-string { color: #b9df8a; }
    .json-number { color: #ffc66d; }
    .json-boolean { color: #e9a7ff; font-weight: 800; }
    .json-null { color: #9a9f98; font-style: italic; }
    .input-tools { display: flex; align-items: center; gap: 9px; margin-top: 10px; flex-wrap: wrap; }
    .input-tools button { padding: 7px 10px; border: 2px solid var(--ink); background: var(--panel); cursor: pointer; font-weight: 800; }
    .input-status { margin-left: auto; font: 700 12px/1.35 "DejaVu Sans Mono", monospace; }
    .input-status.pending { color: #8b5c00; }
    .input-status.valid { color: #13715d; }
    .input-status.invalid { color: #b52d24; }
    .signal-list { display: grid; gap: 15px; }
    .signal-row { border-bottom: 1px solid var(--line); padding-bottom: 12px; }
    .signal-top { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
    .signal-name { font-weight: 800; text-transform: capitalize; }
    .signal-type { color: var(--blue); font: 700 11px/1 "DejaVu Sans Mono", monospace; text-transform: uppercase; }
    .signal-value { margin: 6px 0 7px; font: 700 13px/1.3 "DejaVu Sans Mono", monospace; }
    .policy { padding: 18px; border: 2px solid var(--fun); background: var(--panel); }
    .policy.fallback { border-color: #aa7200; }
    .policy strong { display: block; margin-bottom: 7px; font: 800 16px/1.35 "DejaVu Sans Mono", monospace; }
    .policy p { margin: 5px 0; line-height: 1.5; }
    .policy-meta { color: var(--muted); font-size: 12px; }
    .command { margin-top: 16px; padding: 12px 14px; background: #ded9cc; font: 12px/1.4 "DejaVu Sans Mono", monospace; overflow-x: auto; }
    .run-area { padding: 12px 24px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; border-bottom: 2px solid var(--ink); background: var(--panel); }
    .run-button { padding: 11px 16px; border: 2px solid var(--ink); background: var(--yellow); color: var(--ink); box-shadow: 3px 3px 0 var(--ink); cursor: pointer; font-weight: 800; }
    .run-button:disabled { cursor: wait; opacity: .65; }
    .run-status { margin: 0; color: var(--muted); font: 700 12px/1.4 "DejaVu Sans Mono", monospace; }
    .stage-tracker { flex-basis: 100%; display: flex; gap: 7px; padding: 2px 0 3px; overflow-x: auto; scrollbar-width: thin; }
    .stage-step { flex: 0 0 auto; display: flex; align-items: center; gap: 6px; padding: 6px 8px; border: 1px solid var(--line); color: var(--muted); background: var(--paper); font: 700 10px/1.2 "DejaVu Sans Mono", monospace; }
    .stage-dot { width: 9px; height: 9px; border-radius: 50%; background: #aaa69d; }
    .stage-step.running { color: var(--ink); border-color: var(--blue); }
    .stage-step.running .stage-dot { background: var(--blue); animation: pulse 900ms ease-in-out infinite alternate; }
    .stage-step.completed { color: #13634f; border-color: #17836a; }
    .stage-step.completed .stage-dot { background: #17836a; }
    .stage-step.failed { color: #a82720; border-color: #ce4538; }
    .stage-step.failed .stage-dot { background: #ce4538; }
    .stage-step.skipped { color: #77756e; border-style: dashed; opacity: .72; }
    .stage-step.skipped .stage-dot { background: transparent; border: 2px solid #8d8a82; }
    @keyframes pulse { to { transform: scale(1.45); opacity: .55; } }
    .operation-record { padding: 17px; border: 2px solid var(--ink); background: var(--panel); }
    .operation-record ul { margin: 0; padding-left: 20px; line-height: 1.55; }
    .operation-record pre { max-height: 220px; }
    .source-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
    .source-receipt { padding: 12px; border: 1px solid var(--line); background: var(--paper); }
    .source-receipt strong { display: block; margin-bottom: 6px; }
    .source-receipt span { display: block; color: var(--muted); font: 11px/1.45 "DejaVu Sans Mono", monospace; overflow-wrap: anywhere; }
    .visualizations { min-width: 0; }
    .visual-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr)); gap: 14px; }
    .visual-card { min-width: 0; padding: 14px; border: 2px solid var(--ink); background: var(--panel); }
    .visual-card.pipeline { grid-column: 1 / -1; }
    .visual-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
    .visual-card h4 { margin: 0; font: 800 13px/1.25 "DejaVu Sans Mono", monospace; }
    .chart-tools { display: flex; align-items: center; gap: 4px; }
    .chart-tools button { width: 30px; height: 28px; padding: 0; border: 1px solid var(--ink); background: var(--paper); cursor: pointer; font-weight: 900; }
    .chart-tools button:hover, .chart-tools button:focus-visible { background: var(--yellow); }
    .zoom-readout { min-width: 42px; color: var(--muted); text-align: center; font: 700 10px/1 "DejaVu Sans Mono", monospace; }
    .chart-viewport { position: relative; overflow: hidden; border: 1px solid var(--line); background: #f8f5ed; }
    .visual-card canvas { display: block; width: 100%; height: 280px; cursor: grab; touch-action: none; }
    .visual-card.pipeline canvas { height: 330px; }
    .visual-card canvas.dragging { cursor: grabbing; }
    .chart-hint { position: absolute; right: 8px; bottom: 6px; margin: 0; color: #77756e; background: rgba(248, 245, 237, .88); font: 9px/1.2 "DejaVu Sans Mono", monospace; pointer-events: none; }
    [hidden] { display: none !important; }
    .empty { padding: 48px 0; color: var(--muted); font-weight: 700; }
    @media (max-width: 720px) {
      .topbar { align-items: flex-start; }
      .counter { display: none; }
      .toolbar { align-items: stretch; flex-direction: column; }
      .detail-tabs { padding: 0 8px; overflow: visible; }
      .detail-tab { flex: 1 1 25%; min-width: 0; padding: 9px 4px; font-size: 12px; }
      .detail { max-height: calc(100vh - 292px); }
      .input-layout { grid-template-columns: 1fr; }
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
    <div class="run-area">
      <button id="run" class="run-button" type="button" disabled>Run Jev</button>
      <p id="run-status" class="run-status">Input must pass validation before a live call.</p>
      <div id="stage-tracker" class="stage-tracker" aria-label="Run stage progress"></div>
    </div>
    <div id="detail-tabs" class="detail-tabs" role="tablist" aria-label="Bay details">
      <button id="tab-input" class="detail-tab" type="button" role="tab" aria-selected="true" aria-controls="panel-input" data-tab="input">Input</button>
      <button id="tab-signals" class="detail-tab" type="button" role="tab" aria-selected="false" aria-controls="panel-signals" data-tab="signals">Signals</button>
      <button id="tab-visuals" class="detail-tab" type="button" role="tab" aria-selected="false" aria-controls="panel-visuals" data-tab="visuals" disabled>Visuals</button>
      <button id="tab-decision" class="detail-tab" type="button" role="tab" aria-selected="false" aria-controls="panel-decision" data-tab="decision" disabled>Decision</button>
    </div>
    <div class="detail">
      <section id="panel-input" class="tab-panel input-layout" role="tabpanel" aria-labelledby="tab-input" data-panel="input">
        <div>
          <h3 class="section-title">Run input</h3>
          <div class="editor-shell">
            <pre id="input-highlight" class="input-highlight" aria-hidden="true"></pre>
            <textarea id="detail-state" class="input-editor" aria-label="Editable JSON run input" spellcheck="false" wrap="off"></textarea>
          </div>
          <div class="input-tools">
            <button id="format-input" type="button">Format JSON</button>
            <button id="reset-input" type="button">Reset</button>
            <span id="input-status" class="input-status pending" role="status">Checking input...</span>
          </div>
          <div id="detail-command" class="command"></div>
        </div>
        <section><h3 class="section-title">Question contract</h3><div id="detail-questions" class="signal-list"></div></section>
      </section>
      <section id="panel-signals" class="tab-panel results-layout" role="tabpanel" aria-labelledby="tab-signals" data-panel="signals" hidden>
        <h3 id="signals-heading" class="section-title">Run Jev to inspect typed signals</h3>
        <div id="detail-signals" class="signal-list"></div>
      </section>
      <section id="panel-visuals" class="tab-panel" role="tabpanel" aria-labelledby="tab-visuals" data-panel="visuals" hidden>
        <section id="detail-visualizations" class="visualizations" hidden><h3 class="section-title">Live data visualizations</h3><div id="visualization-grid" class="visual-grid"></div></section>
      </section>
      <section id="panel-decision" class="tab-panel results-layout" role="tabpanel" aria-labelledby="tab-decision" data-panel="decision" hidden>
        <section id="detail-policy" class="policy" hidden><h3 class="section-title">Deterministic policy</h3><strong id="detail-action"></strong><p id="detail-reason"></p><p id="detail-meta" class="policy-meta"></p></section>
        <section id="detail-sources" class="operation-record" hidden><h3 class="section-title">Live source provenance</h3><div id="source-list" class="source-grid"></div></section>
        <section id="detail-controls" class="operation-record" hidden><h3 class="section-title">Non-negotiable controls</h3><ul id="control-list"></ul></section>
        <section id="detail-audit" class="operation-record" hidden><h3 class="section-title">Operation audit</h3><pre id="audit-log"></pre></section>
      </section>
    </div>
  </dialog>
  <script>
    const view = { group: "all", demos: [], current: null };
    const grid = document.querySelector("#grid");
    const status = document.querySelector("#status");
    const detail = document.querySelector("#detail");
    const detailBody = document.querySelector(".detail");
    const tabButtons = [...document.querySelectorAll(".detail-tab")];
    const tabPanels = [...document.querySelectorAll(".tab-panel")];
    const questions = document.querySelector("#detail-questions");
    const signals = document.querySelector("#detail-signals");
    const policy = document.querySelector("#detail-policy");
    const sourcesPanel = document.querySelector("#detail-sources");
    const sourceList = document.querySelector("#source-list");
    const visualizationsPanel = document.querySelector("#detail-visualizations");
    const visualizationGrid = document.querySelector("#visualization-grid");
    const controlsPanel = document.querySelector("#detail-controls");
    const auditPanel = document.querySelector("#detail-audit");
    const inputEditor = document.querySelector("#detail-state");
    const inputHighlight = document.querySelector("#input-highlight");
    const inputStatus = document.querySelector("#input-status");
    const runButton = document.querySelector("#run");
    const runStatus = document.querySelector("#run-status");
    const stageTracker = document.querySelector("#stage-tracker");
    const chartRedraws = new Set();
    let validationTimer;
    let validationVersion = 0;

    function element(tag, className, text) {
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }

    function percent(value) { return `${Math.round(value * 100)}%`; }

    function confidenceColor(value) {
      const bounded = Math.max(0, Math.min(value, 1));
      const hue = Math.round(4 + bounded * 126);
      return `hsl(${hue} 72% 38%)`;
    }

    function setInputStatus(kind, message) {
      inputStatus.className = `input-status ${kind}`;
      inputStatus.textContent = message;
    }

    function initializeStageTracker(steps) {
      stageTracker.replaceChildren();
      steps.forEach((step) => {
        const item = element("div", "stage-step pending");
        item.dataset.stage = step.key;
        item.title = step.label;
        item.append(element("span", "stage-dot"), element("span", "", step.label));
        stageTracker.append(item);
      });
    }

    function updateStage(event) {
      const item = [...stageTracker.children].find((node) => node.dataset.stage === event.key);
      if (!item) return;
      item.className = `stage-step ${event.status}`;
      item.title = event.detail ? `${event.label}: ${event.detail}` : event.label;
      item.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      const complete = stageTracker.querySelectorAll(".completed").length;
      runStatus.textContent = `${complete}/${stageTracker.children.length} complete / ${event.label}`;
    }

    function failRunningStages(message) {
      stageTracker.querySelectorAll(".running").forEach((item) => {
        item.className = "stage-step failed";
        item.title = message;
      });
    }

    function renderJsonHighlight() {
      const source = inputEditor.value;
      const pattern = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
      const fragment = document.createDocumentFragment();
      let cursor = 0;
      for (const match of source.matchAll(pattern)) {
        fragment.append(document.createTextNode(source.slice(cursor, match.index)));
        const token = document.createElement("span");
        if (match[1]) token.className = match[2] ? "json-key" : "json-string";
        else if (match[3] === "null") token.className = "json-null";
        else if (match[3]) token.className = "json-boolean";
        else token.className = "json-number";
        token.textContent = match[0];
        fragment.append(token);
        cursor = match.index + match[0].length;
      }
      fragment.append(document.createTextNode(source.slice(cursor) + "\n"));
      inputHighlight.replaceChildren(fragment);
      inputHighlight.scrollTop = inputEditor.scrollTop;
      inputHighlight.scrollLeft = inputEditor.scrollLeft;
    }

    function setPressed(selector, attribute, value) {
      document.querySelectorAll(selector).forEach((button) => {
        button.setAttribute("aria-pressed", String(button.dataset[attribute] === value));
      });
    }

    function selectTab(name, focus = false) {
      tabButtons.forEach((button) => {
        const active = button.dataset.tab === name;
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
        if (active && focus) button.focus();
      });
      tabPanels.forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
      detailBody.scrollTop = 0;
      if (name === "visuals") requestAnimationFrame(() => chartRedraws.forEach((redraw) => redraw()));
    }

    function setResultTabs(result) {
      document.querySelector("#tab-signals").disabled = false;
      document.querySelector("#tab-decision").disabled = false;
      document.querySelector("#tab-visuals").disabled = !(result.visualizations || []).length;
    }

    function renderQuestions(questions) {
      const target = document.querySelector("#detail-questions");
      target.replaceChildren();
      questions.forEach((question) => {
        const row = element("div", "signal-row");
        const top = element("div", "signal-top");
        top.append(element("span", "signal-name", question.name), element("span", "signal-type", question.type));
        const instructions = typeof question.instructions === "string" ? question.instructions : JSON.stringify(question.instructions);
        row.append(top, element("div", "signal-value", instructions));
        target.append(row);
      });
    }

    function canvasContext(canvas) {
      const ratio = Math.min(devicePixelRatio || 1, 2);
      const width = Math.max(360, Math.floor(canvas.getBoundingClientRect().width));
      const height = Math.max(240, Math.floor(canvas.getBoundingClientRect().height));
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      const context = canvas.getContext("2d");
      context.scale(ratio, ratio);
      context.font = '11px "DejaVu Sans Mono", monospace';
      context.lineWidth = 1.5;
      return { context, width, height };
    }

    function drawVisualization(canvas, visualization, viewport) {
      const { context, width, height } = canvasContext(canvas);
      context.save();
      context.translate(viewport.offsetX, viewport.offsetY);
      context.translate(width / 2, height / 2);
      context.scale(viewport.scale, viewport.scale);
      context.translate(-width / 2, -height / 2);
      if (visualization.kind === "bar") drawBar(context, width, height, visualization.points);
      else if (visualization.kind === "line") drawLine(context, width, height, visualization.points);
      else if (visualization.kind === "map") drawMap(context, width, height, visualization.points);
      else if (visualization.kind === "pipeline") drawPipeline(context, width, height, visualization.points);
      context.restore();
    }

    function drawBar(context, width, height, points) {
      const rows = points.slice(0, 10);
      const left = 118;
      const right = 34;
      const top = 12;
      const rowHeight = (height - 24) / Math.max(rows.length, 1);
      const maximum = Math.max(...rows.map((point) => point.value), 1);
      rows.forEach((point, index) => {
        const y = top + index * rowHeight;
        const barWidth = (width - left - right) * point.value / maximum;
        context.fillStyle = "#65665f";
        context.textAlign = "right";
        context.fillText(point.label.slice(0, 16), left - 8, y + rowHeight * .64);
        context.fillStyle = confidenceColor(point.value / maximum);
        context.fillRect(left, y + 3, barWidth, Math.max(8, rowHeight - 8));
        context.fillStyle = "#171916";
        context.textAlign = "left";
        context.fillText(String(point.value), Math.min(left + barWidth + 6, width - right), y + rowHeight * .64);
      });
    }

    function drawLine(context, width, height, points) {
      const left = 42;
      const top = 16;
      const plotWidth = width - left - 20;
      const plotHeight = height - top - 34;
      const maximum = Math.max(...points.map((point) => point.value), 1);
      context.strokeStyle = "#c8c3b7";
      context.strokeRect(left, top, plotWidth, plotHeight);
      context.beginPath();
      points.forEach((point, index) => {
        const x = left + plotWidth * index / Math.max(points.length - 1, 1);
        const y = top + plotHeight * (1 - point.value / maximum);
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.strokeStyle = "#3674bb";
      context.lineWidth = 3;
      context.stroke();
      points.forEach((point, index) => {
        const x = left + plotWidth * index / Math.max(points.length - 1, 1);
        const y = top + plotHeight * (1 - point.value / maximum);
        context.beginPath();
        context.arc(x, y, 3.2, 0, Math.PI * 2);
        context.fillStyle = confidenceColor(point.value / Math.max(maximum, 5));
        context.fill();
      });
      context.fillStyle = "#68675f";
      context.textAlign = "left";
      context.fillText(points[0]?.label?.slice(0, 16) || "", left, height - 10);
      context.textAlign = "right";
      context.fillText(points.at(-1)?.label?.slice(0, 16) || "", width - 20, height - 10);
    }

    function drawMap(context, width, height, points) {
      const left = 18;
      const top = 12;
      const plotWidth = width - 36;
      const plotHeight = height - 24;
      context.fillStyle = "#e8e3d8";
      context.fillRect(left, top, plotWidth, plotHeight);
      context.strokeStyle = "#c8c3b7";
      for (let longitude = -120; longitude <= 120; longitude += 60) {
        const x = left + (longitude + 180) / 360 * plotWidth;
        context.beginPath(); context.moveTo(x, top); context.lineTo(x, top + plotHeight); context.stroke();
      }
      for (let latitude = -60; latitude <= 60; latitude += 30) {
        const y = top + (90 - latitude) / 180 * plotHeight;
        context.beginPath(); context.moveTo(left, y); context.lineTo(left + plotWidth, y); context.stroke();
      }
      points.forEach((point) => {
        const x = left + (point.x + 180) / 360 * plotWidth;
        const y = top + (90 - point.y) / 180 * plotHeight;
        const radius = Math.max(3, point.value * 1.25);
        context.beginPath();
        context.arc(x, y, radius, 0, Math.PI * 2);
        context.fillStyle = confidenceColor(Math.min(point.value / 8, 1));
        context.globalAlpha = .78;
        context.fill();
        context.globalAlpha = 1;
      });
    }

    function drawPipeline(context, width, height, points) {
      const margin = 46;
      const maxX = Math.max(...points.map((point) => point.x), 1);
      const maxY = Math.max(...points.map((point) => point.y), 1);
      const position = (point) => ({
        x: margin + (width - margin * 2) * point.x / maxX,
        y: margin + (height - margin * 2) * point.y / maxY,
      });
      const layers = [...new Set(points.map((point) => point.x))].sort((a, b) => a - b);
      for (let index = 0; index < layers.length - 1; index += 1) {
        const current = points.filter((point) => point.x === layers[index]);
        const next = points.filter((point) => point.x === layers[index + 1]);
        current.forEach((from) => next.forEach((to) => {
          const start = position(from);
          const end = position(to);
          context.beginPath(); context.moveTo(start.x, start.y); context.lineTo(end.x, end.y);
          context.strokeStyle = "#aaa69d"; context.lineWidth = 1; context.stroke();
        }));
      }
      points.forEach((point) => {
        const location = position(point);
        context.beginPath();
        context.arc(location.x, location.y, 10, 0, Math.PI * 2);
        context.fillStyle = confidenceColor(point.value);
        context.fill();
        context.fillStyle = "#171916";
        context.textAlign = "center";
        context.fillText(point.label.slice(0, 15), location.x, location.y + 25);
      });
    }

    function renderSources(sources) {
      sourceList.replaceChildren();
      sources.forEach((source) => {
        const card = element("div", "source-receipt");
        card.append(
          element("strong", "", source.name),
          element("span", "", `${source.record_count} records`),
          element("span", "", `Updated ${source.source_updated_at}`),
          element("span", "", `SHA-256 ${source.content_sha256.slice(0, 16)}`),
        );
        sourceList.append(card);
      });
      sourcesPanel.hidden = !sources.length;
    }

    function renderVisualizations(visualizations) {
      visualizationGrid.replaceChildren();
      chartRedraws.clear();
      visualizations.forEach((visualization) => {
        const card = element("article", `visual-card ${visualization.kind}`);
        const head = element("div", "visual-head");
        const tools = element("div", "chart-tools");
        const zoomOut = element("button", "", "-");
        const reset = element("button", "", "1:1");
        const zoomIn = element("button", "", "+");
        const readout = element("span", "zoom-readout", "100%");
        zoomOut.type = reset.type = zoomIn.type = "button";
        zoomOut.title = "Zoom out";
        zoomOut.setAttribute("aria-label", "Zoom out");
        reset.title = "Reset zoom and pan";
        reset.setAttribute("aria-label", "Reset zoom and pan");
        zoomIn.title = "Zoom in";
        zoomIn.setAttribute("aria-label", "Zoom in");
        tools.append(zoomOut, reset, zoomIn, readout);
        head.append(element("h4", "", visualization.title), tools);
        const viewportElement = element("div", "chart-viewport");
        const canvas = document.createElement("canvas");
        canvas.tabIndex = 0;
        canvas.setAttribute("role", "img");
        canvas.setAttribute("aria-label", `${visualization.title}. Use plus, minus, zero, mouse wheel, or drag to explore.`);
        viewportElement.append(canvas, element("p", "chart-hint", "wheel / drag / +/- / 0"));
        card.append(head, viewportElement);
        visualizationGrid.append(card);
        const viewport = { scale: 1, offsetX: 0, offsetY: 0, dragging: false, startX: 0, startY: 0 };
        const redraw = () => {
          drawVisualization(canvas, visualization, viewport);
          readout.textContent = `${Math.round(viewport.scale * 100)}%`;
        };
        chartRedraws.add(redraw);
        const setScale = (scale) => {
          viewport.scale = Math.max(.65, Math.min(3, scale));
          redraw();
        };
        const resetView = () => {
          viewport.scale = 1;
          viewport.offsetX = 0;
          viewport.offsetY = 0;
          redraw();
        };
        zoomOut.addEventListener("click", () => setScale(viewport.scale / 1.25));
        zoomIn.addEventListener("click", () => setScale(viewport.scale * 1.25));
        reset.addEventListener("click", resetView);
        canvas.addEventListener("wheel", (event) => {
          event.preventDefault();
          setScale(viewport.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12));
        }, { passive: false });
        canvas.addEventListener("pointerdown", (event) => {
          viewport.dragging = true;
          viewport.startX = event.clientX - viewport.offsetX;
          viewport.startY = event.clientY - viewport.offsetY;
          canvas.classList.add("dragging");
          canvas.setPointerCapture(event.pointerId);
        });
        canvas.addEventListener("pointermove", (event) => {
          if (!viewport.dragging) return;
          viewport.offsetX = event.clientX - viewport.startX;
          viewport.offsetY = event.clientY - viewport.startY;
          redraw();
        });
        const endDrag = (event) => {
          viewport.dragging = false;
          canvas.classList.remove("dragging");
          if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
        };
        canvas.addEventListener("pointerup", endDrag);
        canvas.addEventListener("pointercancel", endDrag);
        canvas.addEventListener("dblclick", resetView);
        canvas.addEventListener("keydown", (event) => {
          if (event.key === "+" || event.key === "=") setScale(viewport.scale * 1.25);
          else if (event.key === "-") setScale(viewport.scale / 1.25);
          else if (event.key === "0") resetView();
          else return;
          event.preventDefault();
        });
        redraw();
        canvas.title = visualization.points.map((point) => `${point.label}: ${point.detail || point.value}`).join("\n");
      });
      visualizationsPanel.hidden = !visualizations.length;
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
        fill.style.backgroundColor = confidenceColor(signal.certainty);
        meter.title = `Certainty: ${percent(signal.certainty)}`;
        meter.append(fill);
        const value = element("div", "signal-value", signal.value);
        value.style.color = confidenceColor(signal.certainty);
        row.append(top, value, meter);
        signals.append(row);
      });
      document.querySelector("#detail-action").textContent = result.decision.action;
      document.querySelector("#detail-reason").textContent = result.decision.reason;
      document.querySelector("#detail-meta").textContent = `Owner: ${result.decision.owner} | policy confidence: ${percent(result.decision.confidence)}`;
      policy.classList.toggle("fallback", result.decision.fallback);
      policy.hidden = false;
      setResultTabs(result);
      renderSources(result.sources || []);
      renderVisualizations(result.visualizations || []);
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
      view.validatedState = null;
      document.querySelector("#detail-group").textContent = demo.group;
      document.querySelector("#detail-title").textContent = demo.title;
      inputEditor.value = JSON.stringify(demo.state, null, 2);
      renderJsonHighlight();
      document.querySelector("#detail-command").textContent = demo.command;
      renderQuestions(demo.questions);
      signals.replaceChildren();
      document.querySelector("#signals-heading").textContent = "Run Jev to inspect typed signals";
      policy.hidden = true;
      sourcesPanel.hidden = true;
      visualizationsPanel.hidden = true;
      controlsPanel.hidden = true;
      auditPanel.hidden = true;
      initializeStageTracker(demo.progress_steps);
      document.querySelector("#tab-signals").disabled = true;
      document.querySelector("#tab-visuals").disabled = true;
      document.querySelector("#tab-decision").disabled = true;
      selectTab("input");
      runButton.disabled = true;
      runButton.textContent = "Run Jev";
      runStatus.textContent = "Input must pass validation before a live call.";
      detail.showModal();
      validateInput();
    }

    async function validateInput() {
      const version = ++validationVersion;
      runButton.disabled = true;
      view.validatedState = null;
      let state;
      try {
        state = JSON.parse(inputEditor.value);
      } catch (error) {
        setInputStatus("invalid", `Invalid JSON: ${error.message}`);
        return false;
      }
      if (!state || Array.isArray(state) || typeof state !== "object") {
        setInputStatus("invalid", "Run input must be a JSON object.");
        return false;
      }
      setInputStatus("pending", "Checking shape...");
      try {
        const response = await fetch(`/api/demos/${view.current.id}/validate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ state }),
        });
        const payload = await response.json();
        if (version !== validationVersion) return false;
        if (!response.ok || !payload.valid) {
          const details = payload.errors?.join("; ") || payload.error || `HTTP ${response.status}`;
          setInputStatus("invalid", details);
          return false;
        }
        view.validatedState = state;
        runButton.disabled = false;
        setInputStatus("valid", `Valid input / ${payload.bytes} bytes`);
        runStatus.textContent = view.current.stage_count > 1
          ? "Ready for staged live evaluation; no operational credentials are available."
          : "Ready for a live TypeSafe call.";
        return true;
      } catch (error) {
        if (version === validationVersion) setInputStatus("invalid", `Validation failed: ${error.message}`);
        return false;
      }
    }

    async function runLive() {
      if (!view.current) return;
      if (!view.validatedState && !(await validateInput())) return;
      initializeStageTracker(view.current.progress_steps);
      runButton.disabled = true;
      runButton.textContent = "Calling Jev...";
      runStatus.textContent = `0/${view.current.progress_steps.length} complete / starting`;
      try {
        const response = await fetch(`/api/demos/${view.current.id}/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "application/x-ndjson" },
          body: JSON.stringify({ state: view.validatedState }),
        });
        if (!response.ok) {
          const payload = await response.json();
          throw new Error(payload.error || `HTTP ${response.status}`);
        }
        if (!response.body) throw new Error("Streaming response body is unavailable");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let resultReceived = false;

        function processLine(line) {
          if (!line.trim()) return;
          const message = JSON.parse(line);
          if (message.type === "progress") updateStage(message.event);
          else if (message.type === "result") {
            renderResult(message.payload);
            resultReceived = true;
          } else if (message.type === "error") {
            throw new Error(message.error);
          }
        }

        while (true) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";
          lines.forEach(processLine);
          if (done) break;
        }
        processLine(buffer);
        if (!resultReceived) throw new Error("Run ended without a final result");
        selectTab("signals");
        runStatus.textContent = "Live result received. No side effect was executed.";
        runButton.textContent = "Run again";
      } catch (error) {
        failRunningStages(error.message);
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
    tabButtons.forEach((button, index) => {
      button.addEventListener("click", () => { if (!button.disabled) selectTab(button.dataset.tab); });
      button.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const enabled = tabButtons.filter((candidate) => !candidate.disabled);
        const current = enabled.indexOf(button);
        let next = current;
        if (event.key === "ArrowRight") next = (current + 1) % enabled.length;
        if (event.key === "ArrowLeft") next = (current - 1 + enabled.length) % enabled.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = enabled.length - 1;
        selectTab(enabled[next].dataset.tab, true);
      });
    });
    inputEditor.addEventListener("input", () => {
      clearTimeout(validationTimer);
      renderJsonHighlight();
      runButton.disabled = true;
      view.validatedState = null;
      setInputStatus("pending", "Input changed / checking...");
      validationTimer = setTimeout(validateInput, 350);
    });
    inputEditor.addEventListener("scroll", () => {
      inputHighlight.scrollTop = inputEditor.scrollTop;
      inputHighlight.scrollLeft = inputEditor.scrollLeft;
    });
    document.querySelector("#format-input").addEventListener("click", () => {
      try {
        inputEditor.value = JSON.stringify(JSON.parse(inputEditor.value), null, 2);
        renderJsonHighlight();
        validateInput();
      } catch (error) {
        setInputStatus("invalid", `Invalid JSON: ${error.message}`);
      }
    });
    document.querySelector("#reset-input").addEventListener("click", () => {
      if (!view.current) return;
      inputEditor.value = JSON.stringify(view.current.state, null, 2);
      renderJsonHighlight();
      validateInput();
    });
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

    def _read_state(self) -> tuple[dict[str, Any], int]:
        content_type = self.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        if content_type != "application/json":
            raise InputPayloadError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise InputPayloadError("Content-Length must be an integer") from error
        if length <= 0:
            raise InputPayloadError("A JSON request body is required")
        if length > MAX_INPUT_BYTES:
            raise InputPayloadError(
                f"Request exceeds the {MAX_INPUT_BYTES}-byte limit",
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InputPayloadError(f"Invalid JSON: {error}") from error
        if not isinstance(payload, dict) or set(payload) != {"state"}:
            raise InputPayloadError("Request body must be an object containing only 'state'")
        state = payload["state"]
        if not isinstance(state, dict):
            raise InputPayloadError("state must be a JSON object")
        state_bytes = len(json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode())
        return state, state_bytes

    def _stream_run(self, demo_id: str, state: dict[str, Any], root: Path) -> None:
        events: Queue[dict[str, Any] | None] = Queue()

        def on_progress(event: ProgressEvent) -> None:
            events.put({"type": "progress", "event": asdict(event)})

        def worker() -> None:
            try:
                payload = run_demo(demo_id, state, root, on_progress)
                events.put({"type": "result", "payload": payload})
            except (SystemExit, TypeSafeError, ValueError) as error:
                events.put({"type": "error", "error": str(error)})
            except Exception as error:  # pragma: no cover - final containment boundary
                events.put({"type": "error", "error": f"Run failed safely: {type(error).__name__}"})
            finally:
                events.put(None)

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        threading.Thread(target=worker, name=f"gallery-run-{demo_id}", daemon=True).start()
        while True:
            event = events.get()
            if event is None:
                break
            try:
                self.wfile.write(json.dumps(event, ensure_ascii=False).encode() + b"\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                break

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

        relative_path = unquote(request.path.removeprefix(prefix)).strip("/")
        validate_only = relative_path.endswith("/validate")
        stream_only = relative_path.endswith("/stream")
        if validate_only:
            demo_id = relative_path.removesuffix("/validate")
        elif stream_only:
            demo_id = relative_path.removesuffix("/stream")
        else:
            demo_id = relative_path
        root = cast(GalleryServer, self.server).gallery_root
        try:
            state, state_bytes = self._read_state()
        except InputPayloadError as error:
            body = json.dumps({"error": str(error)}).encode()
            self._write(error.status, body, "application/json")
            return

        try:
            errors = validate_demo_state(demo_id, state, root)
        except KeyError:
            self._write(HTTPStatus.NOT_FOUND, b'{"error":"unknown demo"}', "application/json")
            return
        if validate_only:
            body = json.dumps({"valid": not errors, "errors": errors, "bytes": state_bytes}).encode()
            self._write(HTTPStatus.OK, body, "application/json")
            return
        if errors:
            body = json.dumps({"error": "Input shape is invalid", "errors": errors}).encode()
            self._write(HTTPStatus.UNPROCESSABLE_ENTITY, body, "application/json")
            return
        if stream_only:
            self._stream_run(demo_id, state, root)
            return

        try:
            payload = run_demo(demo_id, state, root)
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
