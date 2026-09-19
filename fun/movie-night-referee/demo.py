"""Turn a group's preferences into a transparent movie-night recommendation."""

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

TITLE = "Movie night referee"
STATE = {
    "group": [
        "likes clever mysteries, dislikes gore",
        "wants something funny",
        "open to adventure, asleep by 11",
        "prefers subtitles off tonight",
    ],
    "runtime_limit_minutes": 115,
    "recent_watches": ["space opera", "courtroom drama"],
}
QUESTIONS: Questions = {
    "genre": Choice(
        instructions="Choose the genre with the strongest group overlap.",
        criteria={"comedy": None, "mystery": None, "adventure": None, "documentary": None},
    ),
    "intensity": Score(
        instructions="Score the ideal dramatic intensity for tonight.",
        criteria=["cozy", "light", "engaging", "tense", "relentless"],
    ),
    "group_fit": Noul(
        instructions="Is there enough shared preference to make one recommendation?",
        criteria={"true": "A clear overlap exists.", "false": "Preferences remain too divided."},
    ),
}
SIGNALS = SignalNames(choice="genre", score="intensity", noul="group_fit")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.60 or signals.noul < 0.70:
        return PolicyDecision(
            action="Create a three-title shortlist and settle it with one ranked vote.",
            reason="The group overlap is not decisive enough for a single pick.",
            confidence=signals.confidence,
            fallback=True,
            owner="movie-night group",
        )
    return PolicyDecision(
        action=f"Pick a sub-115-minute {signals.choice} at intensity {signals.score:.1f}, with no graphic gore.",
        reason="The house rules convert the typed overlap into a bounded recommendation.",
        confidence=signals.confidence,
        fallback=False,
        owner="remote holder",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
