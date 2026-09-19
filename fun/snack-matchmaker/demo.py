"""Turn a fuzzy craving into one deterministic snack suggestion."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Snack matchmaker"
STATE = {
    "craving": "crunchy, salty, bright, but not a whole meal",
    "time": "late afternoon",
    "pantry": ["popcorn", "miso", "lime", "sesame", "chili flakes", "dark chocolate"],
    "constraints": ["vegetarian", "under 10 minutes"],
}
QUESTIONS: Questions = {
    "flavor": Choice(
        instructions="Choose the flavor profile that best fits the craving and pantry.",
        criteria={"savory": None, "sweet": None, "tangy": None, "smoky": None},
    ),
    "adventure": Score(
        instructions="Score how unusual the snack should feel.",
        criteria=["classic", "familiar", "small twist", "playful", "wild card"],
    ),
    "spice_welcome": Noul(
        instructions="Would a little chili improve this snack?",
        criteria={"true": "Heat complements the stated craving.", "false": "Heat would fight the stated craving."},
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
    flavor = response.choices["flavor"]
    adventure = response.scores["adventure"]
    spice = response.nouls["spice_welcome"]
    confidence = min(flavor.confidence, adventure.confidence, abs(spice.noul - 0.5) * 2)
    if confidence < 0.62:
        return PolicyDecision(
            action="Build a three-bowl tasting flight and let the human choose.",
            reason="The craving signals are charmingly indecisive.",
            confidence=confidence,
            fallback=True,
            owner="snack seeker",
        )
    menu = {
        "savory": "Make miso-lime popcorn with sesame",
        "sweet": "Pair dark chocolate shards with lime zest",
        "tangy": "Toss popcorn with lime and toasted sesame",
        "smoky": "Toast sesame popcorn with a smoky finish",
    }
    heat = " and a pinch of chili" if spice.noul >= 0.70 else ""
    return PolicyDecision(
        action=f"{menu[flavor.choice]}{heat}.",
        reason=f"The {flavor.choice} profile won at adventure level {adventure.score:.1f}.",
        confidence=confidence,
        fallback=False,
        owner="kitchen human",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
