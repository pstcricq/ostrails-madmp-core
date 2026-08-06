"""One ``rules/*.json`` file, and everything that can be wrong with it.

:func:`load_rules_file` is the only entry point, and it validates in three
layers. Never one problem at a time: a failing layer reports everything it
found, and layers 2 and 3 report together. Layer 1 is the exception, and it
is the ordering that makes it one — 2 and 3 read keys it vouched for, so a
document that fails the schema is not carried further.

1. Structural — against :data:`rules/rules.schema.json`: required keys,
   closed ``_cardinality``/``_type`` enumerations, no unknown metadata
   keys, snake_case field names.
2. Coherence — five constraints kept out of the schema on purpose:
    - only ``_type: "object"`` fields may declare child fields, and every
    one of them must declare at least one: an object is its children;
    - ``_allowed_values``/``_suggested_values`` only on scalar fields;
    - never both on the same field: they say opposite things about the
    same list, and the generators read ``_allowed_values`` alone;
    - ``_chapter_description`` only on a *top-level object* field, the
    only kind that becomes a DSW chapter. Anywhere else the generators
    ignore it without a word, which is what this check exists to catch.

   JSON Schema *can* express these, with ``if``/``then`` and a separate
   definition for top-level fields. What it cannot do is say which field is
   wrong and what to write instead: it produces ``'object' should not be
   valid under {'const': 'object'}``. That is the whole reason they are here.
3. Layout — the file declares the standard and the version its own path
   names. Inside the load rather than beside it: a check a caller has to
   remember to run is a check that gets forgotten, and the price is that a
   rules file can only be loaded from ``<standard>/<version>.json``.

Merging files into one tree is not this module's job, nor this package's: it
is done elsewhere, on documents this one has already validated.
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
                f"object field is its children and nothing else. It would "
                f"generate an empty chapter, a gate opening on nothing or "
                f"list items with no question in them, and could never carry "
                f"a value."
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
                f"vocabulary is either closed or recommended, not both. "
                f"field_kind reads _allowed_values first, so the suggested "
                f"values would be silently dropped (keep one)."
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
                f"{path}: _chapter_description but {reason}, only a top-level "
                f"object field becomes a DSW chapter, so anywhere else it "
                f"would be silently ignored (use _description instead)."
            )
        problems.extend(_coherence_problems(node, path, depth + 1))
    return problems


def _layout_problems(path: Path, doc: dict[str, Any]) -> list[str]:
    """Every way the file disagrees with the path it sits at, at once.

    A path names a standard and a version (``<standard>/<version>.json``) and
    the document declares both, in the same spelling — there is no derivation
    between the two, which is the point: a directory and a declaration that
    are the same string cannot drift apart in a way this check has to
    interpret. Without it they drift in silence: a stale directory makes
    provenance name a standard nobody selected, and a file copied to a new
    version filename becomes that version, same content, no record.
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

    Returns the parsed document (``standard``/``extends``/``dmp`` and the
    optional ``description``). Raises :class:`RulesFileError` listing every
    problem found — a path that cannot be read and a syntax error included, so
    that one exception type covers every way a rules file can be wrong and
    callers need catch nothing else. *Which* files to load is a question this
    module does not answer: a caller passes a path.
    """
    try:
        doc = json.loads(Path(path).read_text())
    except OSError as err:
        raise RulesFileError(path, [f"cannot be read: {err.strerror}."]) from err
    except json.JSONDecodeError as err:
        raise RulesFileError(path, [f"invalid JSON: {err}"]) from err
    # Layers 2 and 3 only once the schema passed, and not only to spare the
    # noise: they read doc["standard"], doc["version"] and doc["dmp"] without
    # a guard, which is safe precisely because the schema pass guaranteed the
    # keys are there and typed. A schema-valid document is an object, so
    # nothing else needs asserting here.
    problems = schema_problems(validator_for(SCHEMA_PATH), doc)
    if not problems:
        problems = _coherence_problems(doc["dmp"], "dmp") + _layout_problems(
            Path(path), doc
        )
    if problems:
        raise RulesFileError(path, problems)
    return doc
