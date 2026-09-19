"""Turn a motley fridge shelf into one bounded dinner idea."""

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
SIGNALS = SignalNames(choice="dish", score="ambition", noul="crispy")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.60:
        return PolicyDecision(
            action="Build a warm snack plate and keep every component separate.",
            reason="No single remix has a reliable lead.",
            confidence=signals.confidence,
            fallback=True,
            owner="home cook",
        )
    recipes = {
        "hash": "Crisp the potatoes and leek, crack in the eggs, then finish with feta and parsley",
        "frittata": "Fold the potatoes, leek, and feta into a skillet frittata",
        "flatbread": "Layer the potatoes, leek, and feta over toasted flatbread",
        "salad": "Warm the potatoes and leek, then toss with parsley and feta",
    }
    texture = "; keep the edges deeply crisp" if signals.noul >= 0.70 else ""
    return PolicyDecision(
        action=f"{recipes[signals.choice]}{texture}.",
        reason=f"The {signals.choice} format fits effort level {signals.score:.1f}.",
        confidence=signals.confidence,
        fallback=False,
        owner="home cook",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
