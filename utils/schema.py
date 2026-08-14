"""Generic JSON-Schema validation plumbing, for any package that validates a
data file against a schema.

Depends only on ``jsonschema`` and on ``utils.errors``.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from utils.errors import ProblemsError


class SchemaFileError(ProblemsError):
    """A file is malformed against its schema, with the path as subject.

    Subclassed per domain for a distinct type to catch.
    """

    def __init__(self, path: str | Path, problems: list[str]):
        super().__init__(problems, subject=path)

    @property
    def path(self) -> str:
        """The file the problems are about, ``subject`` in file words."""
        return self.subject


@cache
def _validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(schema_path.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validator_for(schema_path: str | Path) -> Draft202012Validator:
    """A cached validator for a schema file, checked against JSON Schema's own
    meta-schema so a structurally broken schema fails here.

    The path is normalised before it becomes a cache key, which is the only
    reason this wrapper exists: ``@cache`` keys on the argument as given, so
    ``"s.json"`` and ``Path("s.json")`` would each hold a validator for the
    same file.
    """
    return _validator(Path(schema_path))


def schema_problems(validator: Draft202012Validator, doc: Any) -> list[str]:
    """Every schema violation of ``doc``, as sorted ``"path: message"`` strings
    (``"(root)"`` for a top-level problem)."""
    problems = []
    for error in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
        where = ".".join(str(part) for part in error.path) or "(root)"
        problems.append(f"{where}: {error.message}")
    return problems
