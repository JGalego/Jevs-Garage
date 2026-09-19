"""Small shared helpers for loading fixtures and rendering demo results."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rich.console import Console, Group
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typesafe_sdk import Answer, ChoiceAnswer, NoulAnswer, ScoreAnswer, SystemOneResponse, Usage


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """A deterministic application decision made from typed Jev answers."""

    action: str
    reason: str
    confidence: float
    fallback: bool
    owner: str


def fixture_response(path: Path, scenario: str = "confident") -> SystemOneResponse:
    """Load one mocked SDK response from a demo's offline fixture file."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if scenario not in payload:
        available = ", ".join(sorted(payload))
        raise ValueError(f"Unknown fixture scenario {scenario!r}; choose one of: {available}")

    fixture = payload[scenario]
    answers: dict[str, Answer] = {}
    for name, raw_answer in fixture["answers"].items():
        answer_type = raw_answer.get("type")
        if answer_type == "choice":
            answers[name] = ChoiceAnswer.model_validate(raw_answer)
        elif answer_type == "noul":
            answers[name] = NoulAnswer.model_validate(raw_answer)
        elif answer_type == "score":
            normalized = {
                **raw_answer,
                "legend": {int(key): value for key, value in raw_answer["legend"].items()},
                "probabilities": {int(key): value for key, value in raw_answer["probabilities"].items()},
            }
            answers[name] = ScoreAnswer.model_validate(normalized)
        else:
            raise ValueError(f"Unsupported fixture answer type {answer_type!r} for {name!r}")

    return SystemOneResponse(
        model=fixture["model"],
        usage=Usage.model_validate(fixture.get("usage", {})),
        answers=answers,
    )


def require_live_api_key() -> None:
    """Load .env and fail clearly before constructing a live SDK client."""

    load_dotenv()
    if not os.getenv("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is missing. Copy .env.example to .env and add your key.")


def demo_arguments(description: str) -> argparse.Namespace:
    """Parse the consistent two-option CLI used by every tiny demo."""

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--live", action="store_true", help="Call Jev instead of loading an offline fixture.")
    parser.add_argument(
        "--scenario",
        choices=("confident", "uncertain"),
        default="confident",
        help="Offline fixture to display (ignored with --live).",
    )
    return parser.parse_args()


def _answer_rows(response: SystemOneResponse) -> list[tuple[str, str, float]]:
    rows: list[tuple[str, str, float]] = []
    for name, answer in response.answers.items():
        if isinstance(answer, ChoiceAnswer):
            rows.append((name, answer.choice, answer.confidence))
        elif isinstance(answer, ScoreAnswer):
            rows.append((name, f"{answer.score:.1f}", answer.confidence))
        elif isinstance(answer, NoulAnswer):
            rows.append((name, f"yes {answer.noul:.0%}", abs(answer.noul - 0.5) * 2))
    return rows


def _meter(value: float, width: int = 18) -> Text:
    bounded = max(0.0, min(value, 1.0))
    filled = round(bounded * width)
    color = "green" if bounded >= 0.8 else "yellow" if bounded >= 0.6 else "red"
    meter = Text("#" * filled + "-" * (width - filled), style=color)
    meter.append(f" {bounded:>4.0%}", style="bold")
    return meter


def render_demo(
    *,
    title: str,
    group: str,
    state: dict[str, Any],
    response: SystemOneResponse,
    decision: PolicyDecision,
) -> None:
    """Render the state-to-policy path as a compact terminal dashboard."""

    console = Console()
    accent = "red" if group == "CRITICAL" else "green"
    console.print(
        Panel(
            f"[{accent}]JEV'S GARAGE / {group}[/{accent}]\n[bold]{title}[/bold]",
            border_style=accent,
            expand=False,
        )
    )
    console.print("[dim]STATE[/dim] -> [bold cyan]JEV[/bold cyan] -> TYPED RESULT -> POLICY -> ACTION / FALLBACK")
    console.print(Panel(JSON.from_data(state), title="Sample state", border_style="bright_black"))

    signals = Table(title=f"Jev signals / {response.model}", box=None, expand=True)
    signals.add_column("Question", style="bold")
    signals.add_column("Typed answer")
    signals.add_column("Certainty", ratio=2)
    for name, value, confidence in _answer_rows(response):
        signals.add_row(name.replace("_", " "), value, _meter(confidence))

    status = "SAFE FALLBACK" if decision.fallback else "POLICY ACTION"
    status_color = "yellow" if decision.fallback else accent
    decision_text = Group(
        Text(status, style=f"bold {status_color}"),
        Text(decision.action, style="bold"),
        Text(decision.reason),
        Text(f"Owner: {decision.owner} | policy confidence: {decision.confidence:.0%}", style="dim"),
    )
    console.print(signals)
    console.print(Panel(decision_text, title="Deterministic policy", border_style=status_color))
    console.print("[dim]No side effect was executed. This demo only produced a policy recommendation.[/dim]")
