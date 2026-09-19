"""Curate three desk objects into a tiny deterministic exhibition."""

from __future__ import annotations

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import (
    JevSignals,
    PolicyDecision,
    SignalNames,
    render_demo,
    require_live_api_key,
    signals_from_response,
)

TITLE = "Tiny museum curator"
STATE = {
    "objects": [
        {"item": "brass key", "note": "opens nothing anyone remembers"},
        {"item": "tram ticket", "note": "punched 2008"},
        {"item": "blue pencil", "note": "worn down to three centimeters"},
    ],
    "display_space": "one bookshelf",
    "audience": "house guests",
}
QUESTIONS: Questions = {
    "theme": Choice(
        instructions="Choose the strongest curatorial theme connecting these objects.",
        criteria={"memory": None, "journeys": None, "tools": None, "mystery": None},
    ),
    "seriousness": Score(
        instructions="Score how seriously the exhibition should present itself.",
        criteria=["deadpan", "light", "earnest", "scholarly", "monumental"],
    ),
    "coherent": Noul(
        instructions="Do the objects support one coherent exhibition story?",
        criteria={"true": "A shared narrative is visible.", "false": "The objects resist one shared story."},
    ),
}
SIGNALS = SignalNames(choice="theme", score="seriousness", noul="coherent")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.60 or signals.noul < 0.70:
        return PolicyDecision(
            action="Display three open theme cards and let each visitor choose a story.",
            reason="The objects refuse one authoritative interpretation.",
            confidence=signals.confidence,
            fallback=True,
            owner="shelf curator",
        )
    titles = {
        "memory": "Small Evidence of Having Been Here",
        "journeys": "Departures in Brass, Paper, and Blue",
        "tools": "Three Implements, Two Retired",
        "mystery": "The Key, the Ticket, and the Last Blue Line",
    }
    return PolicyDecision(
        action=f'Label the exhibition "{titles[signals.choice]}".',
        reason=f"The cabinet maps {signals.choice} to seriousness {signals.score:.1f}.",
        confidence=signals.confidence,
        fallback=False,
        owner="shelf curator",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
