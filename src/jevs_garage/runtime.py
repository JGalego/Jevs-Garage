"""Small shared helpers for typed policy inputs and terminal rendering."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from rich.console import Console, Group
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typesafe_sdk import ChoiceAnswer, NoulAnswer, ScoreAnswer, SystemOneResponse


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """A deterministic application decision made from typed Jev answers."""

    action: str
    reason: str
    confidence: float
    fallback: bool
    owner: str


@dataclass(frozen=True, slots=True)
class SignalNames:
    """Question names used to extract one choice, score, and noul."""

    choice: str
    score: str
    noul: str


@dataclass(frozen=True, slots=True)
class JevSignals:
    """Plain values consumed by a demo's deterministic policy."""

    choice: str
    choice_confidence: float
    score: float
    score_confidence: float
    noul: float

    @property
    def confidence(self) -> float:
        """Conservative certainty across all three signals."""

        return min(self.choice_confidence, self.score_confidence, abs(self.noul - 0.5) * 2)


def signals_from_response(response: SystemOneResponse, names: SignalNames) -> JevSignals:
    """Extract policy inputs from a real SDK response."""

    choice = response.choices[names.choice]
    score = response.scores[names.score]
    noul = response.nouls[names.noul]
    return JevSignals(
        choice=choice.choice,
        choice_confidence=choice.confidence,
        score=score.score,
        score_confidence=score.confidence,
        noul=noul.noul,
    )


def require_live_api_key() -> None:
    """Load .env and fail clearly before constructing a live SDK client."""

    load_dotenv()
    if not os.getenv("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is missing. Copy .env.example to .env and add your key.")


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
