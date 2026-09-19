"""Map a commute mood to a deterministic playlist recipe."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

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
FIXTURES = Path(__file__).with_name("fixtures.json")


def evaluate(*, live: bool = False, scenario: str = "confident") -> SystemOneResponse:
    if not live:
        return fixture_response(FIXTURES, scenario)
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(response: SystemOneResponse) -> PolicyDecision:
    mood = response.choices["mood"]
    energy = response.scores["energy"]
    instrumental = response.nouls["lyric_free"]
    confidence = min(mood.confidence, energy.confidence, abs(instrumental.noul - 0.5) * 2)
    if confidence < 0.62:
        return PolicyDecision(
            action="Offer four five-minute mood samplers instead of choosing a queue.",
            reason="No single listening mode has a dependable lead.",
            confidence=confidence,
            fallback=True,
            owner="listener",
        )
    vocal_mode = "instrumental" if instrumental.noul >= 0.70 else "vocal-friendly"
    return PolicyDecision(
        action=f"Queue the {mood.choice} circuit at energy {energy.score:.1f}, {vocal_mode} mode.",
        reason="The playlist recipe is selected only from the typed result.",
        confidence=confidence,
        fallback=False,
        owner="music player",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
