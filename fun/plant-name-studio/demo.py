"""Give a houseplant a name through a typed style decision."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

TITLE = "Plant name studio"
STATE = {
    "plant": "Monstera adansonii",
    "look": "small leaves with dramatic oval holes, leaning toward the record shelf",
    "room": "bright reading nook with vintage science-fiction paperbacks",
    "existing_plant_names": ["Mabel", "Basil"],
}
QUESTIONS: Questions = {
    "name_style": Choice(
        instructions="Choose the naming style that fits this plant and room.",
        criteria={"botanical": None, "grandparent": None, "sci_fi": None, "food": None},
    ),
    "weirdness": Score(
        instructions="Score how unusual the name should be.",
        criteria=["plain", "familiar", "quirky", "odd", "magnificently strange"],
    ),
    "easy_to_say": Noul(
        instructions="Should the final name be easy to call across a room?",
        criteria={"true": "Short and pronounceable fits.", "false": "An elaborate name fits."},
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
    style = response.choices["name_style"]
    weirdness = response.scores["weirdness"]
    pronounceable = response.nouls["easy_to_say"]
    confidence = min(style.confidence, weirdness.confidence, abs(pronounceable.noul - 0.5) * 2)
    if confidence < 0.60:
        return PolicyDecision(
            action="Offer the neutral shortlist: Pip, Moss, or Dot.",
            reason="The plant's naming aura has not settled.",
            confidence=confidence,
            fallback=True,
            owner="plant keeper",
        )
    names = {
        "botanical": "Ada Frond",
        "grandparent": "Montgomery",
        "sci_fi": "Ripley",
        "food": "Swiss",
    }
    suffix = " Prime" if weirdness.score >= 3.5 and pronounceable.noul < 0.70 else ""
    return PolicyDecision(
        action=f"Put {names[style.choice]}{suffix} on the little brass nameplate.",
        reason=f"The {style.choice} style won with weirdness set to {weirdness.score:.1f}.",
        confidence=confidence,
        fallback=False,
        owner="plant keeper",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
