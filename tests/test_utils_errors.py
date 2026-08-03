"""utils/errors.py: one error shape for the whole project — every problem of
one attempt, rendered the same way whichever layer raised it."""

import pytest

from utils.errors import ProblemsError


class _Conflict(ProblemsError):
    noun = "rules conflict"


def test_without_a_subject():
    error = ProblemsError(["a: bad", "b: worse"])
    assert str(error) == "2 problem(s):\n  - a: bad\n  - b: worse"
    assert error.subject is None


def test_with_a_subject():
    error = ProblemsError(["bad"], subject="rules/standards/socib/1.0.0.json")
    assert str(error).startswith("rules/standards/socib/1.0.0.json: 1 problem(s):")
    assert error.subject == "rules/standards/socib/1.0.0.json"


def test_a_subclass_names_its_own_problems():
    assert str(_Conflict(["dmp.title: widens"])).startswith("1 rules conflict(s):")


def test_a_path_subject_is_stringified():
    from pathlib import Path

    assert ProblemsError(["bad"], subject=Path("a/b.json")).subject == "a/b.json"


def test_problems_are_copied_not_aliased():
    """The caller usually raises with the very list it accumulated into; the
    error must keep what was raised, whatever the caller does with it after."""
    accumulated = ["first"]
    error = ProblemsError(accumulated)
    accumulated.append("added afterwards")
    assert error.problems == ["first"]


def test_catchable_as_a_value_error():
    with pytest.raises(ValueError):
        raise _Conflict(["anything"])
