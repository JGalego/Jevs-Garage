"""Shared records and terminal rendering for staged Berserk operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from rich.console import Console, Group
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from typesafe_sdk import Questions, SystemOneResponse

from jevs_garage.runtime import PolicyDecision, answer_rows, confidence_meter


@dataclass(frozen=True, slots=True)
class OperationStage:
    """One named Jev evaluation in a larger decision process."""

    key: str
    title: str
    questions: Questions
    response: SystemOneResponse


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Ordered, secret-free evidence about an operation run."""

    sequence: int
    event: str
    detail: str


@dataclass(frozen=True, slots=True)
class OperationRun:
    """A complete staged evaluation with controls and a policy decision."""

    correlation_id: str
    policy_version: str
    state_fingerprint: str
    stages: tuple[OperationStage, ...]
    decision: PolicyDecision
    controls: tuple[str, ...]
    audit: tuple[AuditEvent, ...]

    def __post_init__(self) -> None:
        if not self.correlation_id:
            raise ValueError("correlation_id must not be empty")
        if not self.stages:
            raise ValueError("an operation run requires at least one stage")
        if not self.controls:
            raise ValueError("an operation run requires explicit controls")
        expected = tuple(range(1, len(self.audit) + 1))
        actual = tuple(event.sequence for event in self.audit)
        if actual != expected:
            raise ValueError("audit sequence must be contiguous and start at 1")


def state_fingerprint(state: dict[str, Any]) -> str:
    """Return a stable short digest for correlating an immutable input snapshot."""

    canonical = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def render_operation(*, title: str, state: dict[str, Any], run: OperationRun) -> None:
    """Render a staged operation, controls, audit trail, and final recommendation."""

    console = Console()
    console.print(
        Panel(
            f"[bold yellow]JEV'S GARAGE / BERSERK[/bold yellow]\n[bold]{title}[/bold]",
            border_style="yellow",
            expand=False,
        )
    )
    console.print(
        "[dim]SNAPSHOT[/dim] -> [bold cyan]JEV STAGES[/bold cyan] -> "
        "TYPED EVIDENCE -> POLICY GATE -> RECOMMENDATION / SAFE FALLBACK"
    )
    console.print(Panel(JSON.from_data(state), title="Immutable operation state", border_style="bright_black"))

    for stage in run.stages:
        table = Table(title=f"{stage.title} / {stage.response.model}", box=None, expand=True)
        table.add_column("Question", style="bold")
        table.add_column("Typed answer")
        table.add_column("Certainty", ratio=2)
        for name, value, confidence in answer_rows(stage.response):
            table.add_row(name.replace("_", " "), value, confidence_meter(confidence))
        console.print(table)

    status = "SAFE FALLBACK" if run.decision.fallback else "APPROVAL-GATED RECOMMENDATION"
    status_color = "yellow" if run.decision.fallback else "green"
    decision_text = Group(
        Text(status, style=f"bold {status_color}"),
        Text(run.decision.action, style="bold"),
        Text(run.decision.reason),
        Text(
            f"Owner: {run.decision.owner} | policy confidence: {run.decision.confidence:.0%}",
            style="dim",
        ),
    )
    console.print(Panel(decision_text, title=f"Policy {run.policy_version}", border_style=status_color))

    controls = Table(title="Non-negotiable controls", box=None, expand=True)
    controls.add_column("#", width=3, style="yellow")
    controls.add_column("Control")
    for index, control in enumerate(run.controls, start=1):
        controls.add_row(str(index), control)
    console.print(controls)

    audit = Table(title=f"Audit / {run.correlation_id} / state {run.state_fingerprint}", box=None, expand=True)
    audit.add_column("Seq", width=4)
    audit.add_column("Event", style="bold")
    audit.add_column("Detail", ratio=2)
    for event in run.audit:
        audit.add_row(str(event.sequence), event.event, event.detail)
    console.print(audit)
    console.print("[dim]Dry run only. No production command, notification, or state mutation was executed.[/dim]")
