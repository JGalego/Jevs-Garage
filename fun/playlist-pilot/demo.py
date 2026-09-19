"""Map a commute mood to a deterministic playlist recipe."""

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

TITLE = "Playlist pilot"
STATE = {
    "moment": "rainy train ride before a dense writing session",
    "listener_note": "I need momentum without vocals stealing attention.",
    "duration_minutes": 42,
    "recent_skips": ["arena rock", "spoken word", "slow piano"],
}
QUESTIONS: Questions = {
    "mood": Choice(
        instructions="Choose the playlist mood that best supports this moment.",
        criteria={"focus": None, "lift": None, "unwind": None, "singalong": None},
    ),
    "energy": Score(
        instructions="Score the desired musical energy.",
        criteria=["still", "gentle", "steady", "driving", "maximal"],
    ),
    "lyric_free": Noul(
        instructions="Should the queue favor instrumental tracks?",
        criteria={"true": "Lyrics would compete with the task.", "false": "Lyrics fit the moment."},
    ),
}
SIGNALS = SignalNames(choice="mood", score="energy", noul="lyric_free")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.62:
        return PolicyDecision(
            action="Offer four five-minute mood samplers instead of choosing a queue.",
            reason="No single listening mode has a dependable lead.",
            confidence=signals.confidence,
            fallback=True,
            owner="listener",
        )
    vocal_mode = "instrumental" if signals.noul >= 0.70 else "vocal-friendly"
    return PolicyDecision(
        action=f"Queue the {signals.choice} circuit at energy {signals.score:.1f}, {vocal_mode} mode.",
        reason="The playlist recipe is selected only from the typed result.",
        confidence=signals.confidence,
        fallback=False,
        owner="music player",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
