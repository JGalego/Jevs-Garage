"""Translate a day's forecast and plans into a bounded outfit recipe."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Outfit weather oracle"
STATE = {
    "forecast": {"morning_c": 9, "afternoon_c": 17, "rain_probability": 0.62, "wind_kph": 24},
    "plans": ["cycle 3 km", "office", "outdoor dinner"],
    "closet": ["yellow shell", "denim jacket", "fine-knit jumper", "overshirt", "waterproof shoes"],
    "preference": "colorful, not bulky",
}
QUESTIONS: Questions = {
    "outer_layer": Choice(
        instructions="Choose the most useful outer layer for the whole day.",
        criteria={"shell": None, "denim": None, "overshirt": None, "none": None},
    ),
    "warmth": Score(
        instructions="Score the needed warmth level.",
        criteria=["very light", "light", "layered", "warm", "winter"],
    ),
    "rain_ready": Noul(
        instructions="Should rain protection be part of the outfit?",
        criteria={"true": "Forecast and plans make rain protection useful.", "false": "Rain gear is unnecessary."},
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
    layer = response.choices["outer_layer"]
    warmth = response.scores["warmth"]
    rain = response.nouls["rain_ready"]
    confidence = min(layer.confidence, warmth.confidence, abs(rain.noul - 0.5) * 2)
    if confidence < 0.60:
        return PolicyDecision(
            action="Wear the fine-knit jumper and pack the shell in a small bag.",
            reason="A flexible layer handles the unresolved forecast split.",
            confidence=confidence,
            fallback=True,
            owner="wearer",
        )
    layers = {
        "shell": "yellow shell over the fine-knit jumper",
        "denim": "denim jacket over a light shirt",
        "overshirt": "overshirt over a breathable tee",
        "none": "breathable shirt with no outer layer",
    }
    shoes = "waterproof shoes" if rain.noul >= 0.70 else "regular shoes"
    return PolicyDecision(
        action=f"Wear the {layers[layer.choice]} with {shoes}.",
        reason=f"The closet map combines the selected layer with warmth {warmth.score:.1f}.",
        confidence=confidence,
        fallback=False,
        owner="wearer",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
