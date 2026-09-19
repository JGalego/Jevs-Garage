"""Curate three desk objects into a tiny deterministic exhibition."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

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
FIXTURES = Path(__file__).with_name("fixtures.json")


def evaluate(*, live: bool = False, scenario: str = "confident") -> SystemOneResponse:
    if not live:
        return fixture_response(FIXTURES, scenario)
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(response: SystemOneResponse) -> PolicyDecision:
    theme = response.choices["theme"]
    seriousness = response.scores["seriousness"]
    coherent = response.nouls["coherent"]
    confidence = min(theme.confidence, seriousness.confidence, abs(coherent.noul - 0.5) * 2)
    if confidence < 0.60 or coherent.noul < 0.70:
        return PolicyDecision(
            action="Display three open theme cards and let each visitor choose a story.",
            reason="The objects refuse one authoritative interpretation.",
            confidence=confidence,
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
        action=f'Label the exhibition "{titles[theme.choice]}".',
        reason=f"The cabinet maps {theme.choice} to seriousness {seriousness.score:.1f}.",
        confidence=confidence,
        fallback=False,
        owner="shelf curator",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
