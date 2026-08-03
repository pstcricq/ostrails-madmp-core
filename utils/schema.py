"""Generic JSON-Schema validation plumbing, shared by ``rules/`` and
``configs/``.

Depends only on ``jsonschema`` and on :mod:`utils.errors`, so both packages can
build on it without coupling to each other. Each keeps its own schema file, its
own ``…FileError`` subclass, and any domain-specific checks (rules' coherence
pass); only the mechanics live here.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from utils.errors import ProblemsError


class SchemaFileError(ProblemsError):
    """A file is malformed against its schema. Subclassed per domain
    (``RulesFileError``, ``ConfigFileError``) for a distinct type to catch.

    Takes the path first, because for a file error that is the subject.
    """

    def __init__(self, path: str | Path, problems: list[str]):
        super().__init__(problems, subject=path)

    @property
    def path(self) -> str:
        """The file the problems are about — :attr:`subject` in file words."""
        return self.subject


@cache
def validator_for(schema_path: str | Path) -> Draft202012Validator:
    """A cached validator for a schema file — meta-checked against JSON Schema's
    own meta-schema, so a structurally broken schema fails here rather than
    silently mis-validating real files."""
    schema = json.loads(Path(schema_path).read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_problems(validator: Draft202012Validator, doc: Any) -> list[str]:
    """Every schema violation of ``doc``, as sorted ``"path: message"`` strings
    (``"(root)"`` for a top-level problem)."""
    problems = []
    for error in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
        where = ".".join(str(part) for part in error.path) or "(root)"
        problems.append(f"{where}: {error.message}")
    return problems
