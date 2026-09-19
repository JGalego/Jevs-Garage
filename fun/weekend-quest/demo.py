"""Choose a small weekend adventure from the day's actual state."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

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
FIXTURES = Path(__file__).with_name("fixtures.json")


def evaluate(*, live: bool = False, scenario: str = "confident") -> SystemOneResponse:
    if not live:
        return fixture_response(FIXTURES, scenario)
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(response: SystemOneResponse) -> PolicyDecision:
    quest = response.choices["quest_type"]
    commitment = response.scores["commitment"]
    outdoors = response.nouls["outdoors"]
    confidence = min(quest.confidence, commitment.confidence, abs(outdoors.noul - 0.5) * 2)
    if confidence < 0.60:
        return PolicyDecision(
            action="Flip a coin: riverside photo walk or one-room local museum.",
            reason="The day has two equally plausible shapes.",
            confidence=confidence,
            fallback=True,
            owner="weekend crew",
        )
    quests = {
        "nature": "Follow the old canal path and photograph five signs of seasonal change",
        "culture": "Visit one small museum and sketch the strangest object",
        "food": "Build a three-stop neighborhood tasting route",
        "wandering": "Take the next tram to an unfamiliar final stop and walk back",
    }
    mode = "mostly outdoors" if outdoors.noul >= 0.70 else "with an indoor anchor"
    return PolicyDecision(
        action=f"{quests[quest.choice]}, {mode}.",
        reason=f"The quest board matched {quest.choice} with commitment {commitment.score:.1f}.",
        confidence=confidence,
        fallback=False,
        owner="weekend crew",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
