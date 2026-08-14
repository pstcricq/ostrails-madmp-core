"""One ``rules/*.json`` file, and everything that can be wrong with it.

``load_rules_file()`` is the only entry point. It validates in three
layers, and a failing layer reports every problem it found rather than the
first one:

1. Structural, against ``rules.schema.json``: required keys, closed
   ``_cardinality``/``_type`` enumerations, no unknown metadata keys,
   snake_case field names.
2. Coherence, five constraints checked here rather than in the schema: only
   ``_type: "object"`` fields may declare child fields, every one of them
   must declare at least one, ``_allowed_values``/``_suggested_values`` only
   on scalar fields, never both on the same field, and
   ``_chapter_description`` only on a top-level object field.
3. Layout: the document declares the standard and the version its own path
   names, so a rules file can only be loaded from
   ``<standard>/<version>.json``.

Layers 2 and 3 read keys layer 1 vouched for, so they run only once it
passed, and they report together.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.schema import SchemaFileError, schema_problems, validator_for

SCHEMA_PATH = Path(__file__).with_name("rules.schema.json")


class RulesFileError(SchemaFileError):
    """A rules file is malformed (schema or coherence)."""


def field_children(node: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """A field node's declared child fields: every key not starting with ``_``."""
    return [(k, v) for k, v in node.items() if not k.startswith("_")]


def _coherence_problems(tree: dict[str, Any], prefix: str, depth: int = 1) -> list[str]:
    """Every coherence constraint broken in a field tree, at once.

    ``prefix`` is the dotted path of ``tree``, ``depth`` its level, 1 for
    ``dmp``'s own fields.
    """
    problems = []
    for key, node in field_children(tree):
        path = f"{prefix}.{key}"
        if field_children(node) and node.get("_type") != "object":
            problems.append(
                f"{path}: declares child fields but has _type "
                f"{node.get('_type')!r}, only 'object' fields may have children."
            )
        if node.get("_type") == "object" and not field_children(node):
            problems.append(
                f"{path}: _type 'object' but declares no child fields, an "
                f"object field must declare at least one."
            )
        for vocab_key in ("_allowed_values", "_suggested_values"):
            if vocab_key in node and node.get("_type") == "object":
                problems.append(
                    f"{path}: {vocab_key} on an 'object' field, vocabularies "
                    f"only apply to scalar fields."
                )
        if "_allowed_values" in node and "_suggested_values" in node:
            problems.append(
                f"{path}: both _allowed_values and _suggested_values, a "
                f"vocabulary is either closed or recommended, not both "
                f"(keep one)."
            )
        if "_chapter_description" in node and not (
            depth == 1 and node.get("_type") == "object"
        ):
            reason = (
                f"_type {node.get('_type')!r} is not an object"
                if depth == 1
                else "it is not a top-level field"
            )
            problems.append(
                f"{path}: _chapter_description but {reason} (use _description instead)."
            )
        problems.extend(_coherence_problems(node, path, depth + 1))
    return problems


def _layout_problems(path: Path, doc: dict[str, Any]) -> list[str]:
    """Every way the file disagrees with the path it sits at, at once.

    ``<standard>/<version>.json``: the directory name must equal the declared
    ``standard``, and the file stem the declared ``version``, string for
    string.
    """
    problems = []
    if doc["standard"] != path.parent.name:
        problems.append(
            f"declares standard {doc['standard']!r} but sits in directory "
            f"{path.parent.name!r}, the two must agree."
        )
    if doc["version"] != path.stem:
        problems.append(
            f"declares version {doc['version']!r} but is named {path.stem!r}, "
            f"the two must agree."
        )
    return problems


def load_rules_file(path: str | Path) -> dict[str, Any]:
    """Load one ``rules.json`` file, fully validated.

    Returns the parsed document (``standard``, ``extends``, ``dmp`` and the
    optional ``description``). Raises ``RulesFileError`` listing every
    problem found, an unreadable path and a syntax error included, so a
    caller needs to catch nothing else.
    """
    try:
        doc = json.loads(Path(path).read_text())
    except OSError as err:
        raise RulesFileError(path, [f"cannot be read: {err.strerror}."]) from err
    except json.JSONDecodeError as err:
        raise RulesFileError(path, [f"invalid JSON: {err}"]) from err
    # Layers 2 and 3 read doc["standard"], doc["version"] and doc["dmp"]
    # unguarded, which the schema pass has just guaranteed to be there and
    # typed, so they only run when it found nothing.
    problems = schema_problems(validator_for(SCHEMA_PATH), doc)
    if not problems:
        problems = _coherence_problems(doc["dmp"], "dmp") + _layout_problems(
            Path(path), doc
        )
    if problems:
        raise RulesFileError(path, problems)
    return doc
