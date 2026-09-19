"""Assertions shared by each demo's colocated tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from typesafe_sdk import Choice, ChoiceAnswer, Noul, NoulAnswer, Questions, Score, ScoreAnswer, SystemOneResponse

from jevs_garage.runtime import SignalNames


def load_demo(path: Path) -> ModuleType:
    """Load a hyphenated demo folder without turning demos into a framework."""

    module_name = f"garage_demo_{path.parent.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load demo module at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def assert_question_contract(questions: Questions, names: SignalNames) -> None:
    """Verify a demo declares one typed SDK question for each policy signal."""

    assert set(questions) == {names.choice, names.score, names.noul}
    choice = questions[names.choice]
    score = questions[names.score]
    noul = questions[names.noul]
    assert isinstance(choice, Choice)
    assert isinstance(score, Score)
    assert isinstance(noul, Noul)
    assert choice.model_dump()["type"] == "choice"
    assert score.model_dump()["type"] == "score"
    assert noul.model_dump()["type"] == "noul"


def assert_response_contract(questions: Questions, response: SystemOneResponse) -> None:
    """Verify an actual Jev response matches its declared SDK questions."""

    assert set(response.answers) == set(questions)
    for name, question in questions.items():
        question_type = question["type"] if isinstance(question, dict) else question.type
        answer = response.answers[name]
        assert answer.type == question_type
        if isinstance(answer, ChoiceAnswer):
            assert answer.choice in answer.probabilities
            assert sum(answer.probabilities.values()) == pytest.approx(1, abs=0.02)
        elif isinstance(answer, ScoreAnswer):
            assert set(answer.legend) == set(answer.probabilities)
            assert sum(answer.probabilities.values()) == pytest.approx(1, abs=0.02)
        elif isinstance(answer, NoulAnswer):
            assert 0 <= answer.noul <= 1
