from __future__ import annotations

from pathlib import Path

import pytest

from jevs_garage.gallery import discover_demo_paths
from jevs_garage.runtime import signals_from_response
from tests.support import assert_response_contract, load_demo

DEMO_PATHS = discover_demo_paths()


@pytest.mark.live
@pytest.mark.parametrize(
    ("group", "path"),
    DEMO_PATHS,
    ids=[f"{group}/{path.parent.name}" for group, path in DEMO_PATHS],
)
def test_demo_against_typesafe_api(group: str, path: Path) -> None:
    module = load_demo(path)
    if hasattr(module, "execute"):
        operation = module.execute()
        for stage in operation.stages:
            assert_response_contract(module.QUESTION_SETS[stage.key], stage.response)
        decision = operation.decision
        assert operation.controls
        assert operation.audit[-1].event == "execution.blocked"
    else:
        response = module.evaluate()
        assert_response_contract(module.QUESTIONS, response)
        decision = module.decide(signals_from_response(response, module.SIGNALS))
    assert decision.action
    assert decision.reason
    assert decision.owner
    assert 0 <= decision.confidence <= 1
    assert group in {"critical", "berserk", "fun"}
