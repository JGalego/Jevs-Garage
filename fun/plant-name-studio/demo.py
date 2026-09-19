"""Give a houseplant a name through a typed style decision."""

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
SIGNALS = SignalNames(choice="name_style", score="weirdness", noul="easy_to_say")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.60:
        return PolicyDecision(
            action="Offer the neutral shortlist: Pip, Moss, or Dot.",
            reason="The plant's naming aura has not settled.",
            confidence=signals.confidence,
            fallback=True,
            owner="plant keeper",
        )
    names = {
        "botanical": "Ada Frond",
        "grandparent": "Montgomery",
        "sci_fi": "Ripley",
        "food": "Swiss",
    }
    suffix = " Prime" if signals.score >= 3.5 and signals.noul < 0.70 else ""
    return PolicyDecision(
        action=f"Put {names[signals.choice]}{suffix} on the little brass nameplate.",
        reason=f"The {signals.choice} style won with weirdness set to {signals.score:.1f}.",
        confidence=signals.confidence,
        fallback=False,
        owner="plant keeper",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
