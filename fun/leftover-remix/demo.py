"""Turn a motley fridge shelf into one bounded dinner idea."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Leftover remix station"
STATE = {
    "fridge": ["roast potatoes", "half a leek", "two eggs", "parsley", "feta"],
    "pantry": ["smoked paprika", "flatbread", "olive oil"],
    "time_minutes": 22,
    "mood": "warm, savory, minimum washing up",
}
QUESTIONS: Questions = {
    "dish": Choice(
        instructions="Choose the best dish format for these leftovers and constraints.",
        criteria={"hash": None, "frittata": None, "flatbread": None, "salad": None},
    ),
    "ambition": Score(
        instructions="Score the appropriate cooking effort.",
        criteria=["assemble", "one pan", "easy cook", "project", "showpiece"],
    ),
    "crispy": Noul(
        instructions="Is a crisp texture central to satisfying this meal?",
        criteria={
            "true": "Crispness strongly fits the ingredients and mood.",
            "false": "A softer preparation fits better.",
        },
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
    dish = response.choices["dish"]
    ambition = response.scores["ambition"]
    crispy = response.nouls["crispy"]
    confidence = min(dish.confidence, ambition.confidence, abs(crispy.noul - 0.5) * 2)
    if confidence < 0.60:
        return PolicyDecision(
            action="Build a warm snack plate and keep every component separate.",
            reason="No single remix has a reliable lead.",
            confidence=confidence,
            fallback=True,
            owner="home cook",
        )
    recipes = {
        "hash": "Crisp the potatoes and leek, crack in the eggs, then finish with feta and parsley",
        "frittata": "Fold the potatoes, leek, and feta into a skillet frittata",
        "flatbread": "Layer the potatoes, leek, and feta over toasted flatbread",
        "salad": "Warm the potatoes and leek, then toss with parsley and feta",
    }
    texture = "; keep the edges deeply crisp" if crispy.noul >= 0.70 else ""
    return PolicyDecision(
        action=f"{recipes[dish.choice]}{texture}.",
        reason=f"The {dish.choice} format fits effort level {ambition.score:.1f}.",
        confidence=confidence,
        fallback=False,
        owner="home cook",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
