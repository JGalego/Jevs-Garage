"""Turn a fuzzy craving into one deterministic snack suggestion."""

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
SIGNALS = SignalNames(choice="flavor", score="adventure", noul="spice_welcome")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.62:
        return PolicyDecision(
            action="Build a three-bowl tasting flight and let the human choose.",
            reason="The craving signals are charmingly indecisive.",
            confidence=signals.confidence,
            fallback=True,
            owner="snack seeker",
        )
    menu = {
        "savory": "Make miso-lime popcorn with sesame",
        "sweet": "Pair dark chocolate shards with lime zest",
        "tangy": "Toss popcorn with lime and toasted sesame",
        "smoky": "Toast sesame popcorn with a smoky finish",
    }
    heat = " and a pinch of chili" if signals.noul >= 0.70 else ""
    return PolicyDecision(
        action=f"{menu[signals.choice]}{heat}.",
        reason=f"The {signals.choice} profile won at adventure level {signals.score:.1f}.",
        confidence=signals.confidence,
        fallback=False,
        owner="kitchen human",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
