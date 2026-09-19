"""Choose a small weekend adventure from the day's actual state."""

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

TITLE = "Weekend quest board"
STATE = {
    "weather": "clear, 19 C, breezy after 16:00",
    "energy": "curious but not athletic",
    "company": "two friends and one camera",
    "radius_km": 18,
    "available_hours": 4,
    "recent_outings": ["cinema", "long brunch"],
}
QUESTIONS: Questions = {
    "quest_type": Choice(
        instructions="Choose the outing style that best fits the day's constraints.",
        criteria={"nature": None, "culture": None, "food": None, "wandering": None},
    ),
    "commitment": Score(
        instructions="Score how much planning and effort the outing should require.",
        criteria=["step outside", "tiny", "easy", "half-day", "expedition"],
    ),
    "outdoors": Noul(
        instructions="Should most of the outing happen outdoors?",
        criteria={"true": "Weather and mood favor being outside.", "false": "An indoor plan fits better."},
    ),
}
SIGNALS = SignalNames(choice="quest_type", score="commitment", noul="outdoors")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.60:
        return PolicyDecision(
            action="Flip a coin: riverside photo walk or one-room local museum.",
            reason="The day has two equally plausible shapes.",
            confidence=signals.confidence,
            fallback=True,
            owner="weekend crew",
        )
    quests = {
        "nature": "Follow the old canal path and photograph five signs of seasonal change",
        "culture": "Visit one small museum and sketch the strangest object",
        "food": "Build a three-stop neighborhood tasting route",
        "wandering": "Take the next tram to an unfamiliar final stop and walk back",
    }
    mode = "mostly outdoors" if signals.noul >= 0.70 else "with an indoor anchor"
    return PolicyDecision(
        action=f"{quests[signals.choice]}, {mode}.",
        reason=f"The quest board matched {signals.choice} with commitment {signals.score:.1f}.",
        confidence=signals.confidence,
        fallback=False,
        owner="weekend crew",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
