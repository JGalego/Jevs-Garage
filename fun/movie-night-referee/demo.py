"""Turn a group's preferences into a transparent movie-night recommendation."""

from __future__ import annotations

from pathlib import Path

from typesafe_sdk import Choice, Noul, Questions, Score, SystemOneResponse, TypeSafeClient

from jevs_garage.runtime import PolicyDecision, demo_arguments, fixture_response, render_demo, require_live_api_key

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
FIXTURES = Path(__file__).with_name("fixtures.json")


def evaluate(*, live: bool = False, scenario: str = "confident") -> SystemOneResponse:
    if not live:
        return fixture_response(FIXTURES, scenario)
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(response: SystemOneResponse) -> PolicyDecision:
    genre = response.choices["genre"]
    intensity = response.scores["intensity"]
    fit = response.nouls["group_fit"]
    confidence = min(genre.confidence, intensity.confidence, abs(fit.noul - 0.5) * 2)
    if confidence < 0.60 or fit.noul < 0.70:
        return PolicyDecision(
            action="Create a three-title shortlist and settle it with one ranked vote.",
            reason="The group overlap is not decisive enough for a single pick.",
            confidence=confidence,
            fallback=True,
            owner="movie-night group",
        )
    return PolicyDecision(
        action=f"Pick a sub-115-minute {genre.choice} at intensity {intensity.score:.1f}, with no graphic gore.",
        reason="The house rules convert the typed overlap into a bounded recommendation.",
        confidence=confidence,
        fallback=False,
        owner="remote holder",
    )


def main() -> None:
    args = demo_arguments(__doc__ or TITLE)
    response = evaluate(live=args.live, scenario=args.scenario)
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decide(response))


if __name__ == "__main__":
    main()
