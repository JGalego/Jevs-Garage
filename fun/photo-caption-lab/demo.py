"""Choose a caption from typed tone signals, not free-form generation."""

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

TITLE = "Photo caption lab"
STATE = {
    "photo": "A tiny espresso cup on a huge empty cafe table, morning sun making a long shadow.",
    "destination": "friends-only photo album",
    "author_style": "dry, brief, not sentimental",
    "occasion": "first coffee after an overnight train",
}
QUESTIONS: Questions = {
    "voice": Choice(
        instructions="Choose the caption voice that best fits the photo and author.",
        criteria={"dry": None, "warm": None, "dramatic": None, "observational": None},
    ),
    "playfulness": Score(
        instructions="Score how playful the caption should be.",
        criteria=["literal", "restrained", "wry", "silly", "absurd"],
    ),
    "pun": Noul(
        instructions="Would a coffee pun improve this caption?",
        criteria={"true": "A pun fits the author and scene.", "false": "A pun would feel forced."},
    ),
}
SIGNALS = SignalNames(choice="voice", score="playfulness", noul="pun")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.60:
        return PolicyDecision(
            action='Use the plain caption: "First coffee after the night train."',
            reason="Tone uncertainty favors a caption that cannot overreach.",
            confidence=signals.confidence,
            fallback=True,
            owner="photo owner",
        )
    captions = {
        "dry": "Table for one, coffee for several.",
        "warm": "A small cup and a very welcome morning.",
        "dramatic": "At dawn, the espresso arrived.",
        "observational": "The coffee occupied roughly two percent of the table.",
    }
    caption = captions[signals.choice]
    if signals.noul >= 0.75:
        caption = "Taking the express-o after the overnight train."
    return PolicyDecision(
        action=f'Use the caption: "{caption}"',
        reason=f"The caption deck matched {signals.choice} voice at playfulness {signals.score:.1f}.",
        confidence=signals.confidence,
        fallback=False,
        owner="photo owner",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
