"""Assertions shared by each demo's colocated tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from typesafe_sdk import ChoiceAnswer, NoulAnswer, Questions, ScoreAnswer, SystemOneResponse


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


def assert_model_contract(questions: Questions, response: SystemOneResponse) -> None:
    """Verify fixture answers match the SDK question types and probability invariants."""

    assert set(response.answers) == set(questions)
    for name, question in questions.items():
        question_type = question["type"] if isinstance(question, dict) else question.type
        answer = response.answers[name]
        assert answer.type == question_type
        if isinstance(answer, ChoiceAnswer):
            assert answer.choice in answer.probabilities
            assert answer.confidence == pytest.approx(answer.probabilities[answer.choice], abs=0.15)
            assert sum(answer.probabilities.values()) == pytest.approx(1, abs=0.02)
        elif isinstance(answer, ScoreAnswer):
            assert set(answer.legend) == set(answer.probabilities)
            assert sum(answer.probabilities.values()) == pytest.approx(1, abs=0.02)
        elif isinstance(answer, NoulAnswer):
            assert 0 <= answer.noul <= 1
