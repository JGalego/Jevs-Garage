"""Choose a tabletop sidekick from typed party dynamics."""

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

TITLE = "Tabletop sidekick forge"
STATE = {
    "party": ["earnest knight", "stormy sorcerer", "talkative bard"],
    "adventure": "museum heist during a royal masquerade",
    "session_hours": 3,
    "group_note": "We need clues and utility, not another spotlight magnet.",
}
QUESTIONS: Questions = {
    "role": Choice(
        instructions="Choose the role that best complements this party.",
        criteria={"healer": None, "scout": None, "defender": None, "trickster": None},
    ),
    "chaos": Score(
        instructions="Score how chaotic the sidekick should be.",
        criteria=["steadfast", "calm", "wry", "mischievous", "uncontained"],
    ),
    "team_fit": Noul(
        instructions="Does one role clearly fill a gap without duplicating the party?",
        criteria={"true": "A complementary gap is clear.", "false": "The party needs are ambiguous."},
    ),
}
SIGNALS = SignalNames(choice="role", score="chaos", noul="team_fit")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.62 or signals.noul < 0.70:
        return PolicyDecision(
            action="Lay out three character cards and let the table vote.",
            reason="The missing party role is not clear enough for one pick.",
            confidence=signals.confidence,
            fallback=True,
            owner="game master",
        )
    characters = {
        "healer": "Tamsin, tea-brewing field medic",
        "scout": "Mira Quickstep, museum-map enthusiast",
        "defender": "Ors, retired palace door",
        "trickster": "Nix, licensed distraction",
    }
    return PolicyDecision(
        action=f"Add {characters[signals.choice]} at chaos level {signals.score:.1f}.",
        reason="The character shelf maps the typed party gap to a bounded option.",
        confidence=signals.confidence,
        fallback=False,
        owner="game master",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="FUN", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
