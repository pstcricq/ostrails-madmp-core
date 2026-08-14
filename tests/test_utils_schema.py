"""utils/schema.py: the shared JSON-Schema plumbing. Validators are
meta-checked and cached, and every violation of a document is reported at once
as a readable "path: message"."""

import json
from pathlib import Path

import pytest
from jsonschema.exceptions import SchemaError

from utils.schema import SchemaFileError, schema_problems, validator_for

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "tags"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


def _schema_file(tmp_path, schema, name="schema.json"):
    path = tmp_path / name
    path.write_text(json.dumps(schema))
    return path


def test_valid_document_has_no_problems(tmp_path):
    validator = validator_for(_schema_file(tmp_path, SCHEMA))
    assert schema_problems(validator, {"name": "a", "tags": ["x"]}) == []


def test_validator_is_cached_per_path(tmp_path):
    path = _schema_file(tmp_path, SCHEMA)
    assert validator_for(path) is validator_for(path)


def test_the_cache_key_is_the_file_not_how_it_was_spelled(tmp_path):
    """A cache keyed on the argument as given would hold one validator per
    spelling of the same path."""
    path = _schema_file(tmp_path, SCHEMA)
    assert validator_for(str(path)) is validator_for(Path(path))


def test_broken_schema_fails_at_build_time(tmp_path):
    # `minLength: "no"` is not a valid schema, check_schema must catch it
    # here rather than let it mis-validate real files later.
    broken = {"type": "object", "properties": {"name": {"minLength": "no"}}}
    with pytest.raises(SchemaError):
        validator_for(_schema_file(tmp_path, broken, "broken.json"))


def test_top_level_problem_is_reported_at_root(tmp_path):
    validator = validator_for(_schema_file(tmp_path, SCHEMA))
    (problem,) = schema_problems(validator, {"tags": []})
    assert problem.startswith("(root): ")
    assert "name" in problem


def test_nested_problem_carries_its_path(tmp_path):
    validator = validator_for(_schema_file(tmp_path, SCHEMA))
    problems = schema_problems(validator, {"name": "a", "tags": ["x", 2]})
    assert any(p.startswith("tags.1: ") for p in problems), problems


def test_every_problem_is_reported_not_just_the_first(tmp_path):
    validator = validator_for(_schema_file(tmp_path, SCHEMA))
    problems = schema_problems(validator, {"name": "", "tags": "nope", "extra": 1})
    assert len(problems) == 3, problems


def test_error_carries_path_and_problems():
    error = SchemaFileError("some/file.yaml", ["a: bad", "b: worse"])
    assert error.path == "some/file.yaml"
    assert error.problems == ["a: bad", "b: worse"]
    message = str(error)
    assert "some/file.yaml" in message
    assert "2 problem(s)" in message
    assert "a: bad" in message and "b: worse" in message
