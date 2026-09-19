"""Verify an AI-authored claim before publication."""

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

TITLE = "AI output verification bay"
STATE = {
    "claim": "Quarterly revenue increased by 18 percent year over year.",
    "citation": "Q3 finance summary, table 2: revenue growth was 8 percent year over year.",
    "document_status": "draft shareholder update",
    "claim_has_inline_citation": True,
}
QUESTIONS: Questions = {
    "verdict": Choice(
        instructions="Classify how the cited evidence relates to the claim.",
        criteria={
            "supported": "The evidence directly supports the claim.",
            "contradicted": "The evidence directly conflicts with the claim.",
            "insufficient": "The evidence does not settle the claim.",
        },
    ),
    "reliability": Score(
        instructions="Score the claim's reliability for publication.",
        criteria=["false", "poor", "uncertain", "credible", "verified"],
    ),
    "citation_support": Noul(
        instructions="Does the citation support the exact numerical claim?",
        criteria={
            "true": "The source supports the stated number.",
            "false": "The source does not support the stated number.",
        },
    ),
}
SIGNALS = SignalNames(choice="verdict", score="reliability", noul="citation_support")


def evaluate() -> SystemOneResponse:
    require_live_api_key()
    with TypeSafeClient() as client:
        return client.system_one(state=STATE, questions=QUESTIONS)


def decide(signals: JevSignals) -> PolicyDecision:
    if signals.confidence < 0.80 or signals.choice == "insufficient":
        return PolicyDecision(
            action="Keep the claim in draft and request a human fact check.",
            reason="Evidence support is too uncertain for publication.",
            confidence=signals.confidence,
            fallback=True,
            owner="fact checker",
        )
    if signals.choice == "contradicted" or signals.noul <= 0.15 or signals.score <= 1:
        return PolicyDecision(
            action="Block publication of the claim and attach the conflicting source excerpt.",
            reason="High-confidence typed results show a direct evidence conflict.",
            confidence=signals.confidence,
            fallback=False,
            owner="editor",
        )
    if signals.choice == "supported" and signals.noul >= 0.90 and signals.score >= 3.5:
        return PolicyDecision(
            action="Mark the claim verified for the editorial release queue.",
            reason="The claim passes all configured evidence thresholds.",
            confidence=signals.confidence,
            fallback=False,
            owner="editorial workflow",
        )
    return PolicyDecision(
        action="Keep the claim in draft for standard source review.",
        reason="Evidence is plausible but below the verified-release boundary.",
        confidence=signals.confidence,
        fallback=False,
        owner="editor",
    )


def main() -> None:
    response = evaluate()
    decision = decide(signals_from_response(response, SIGNALS))
    render_demo(title=TITLE, group="CRITICAL", state=STATE, response=response, decision=decision)


if __name__ == "__main__":
    main()
