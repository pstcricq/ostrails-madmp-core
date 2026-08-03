"""One ``rules/*.json`` file, and everything that can be wrong with it.

:func:`load_rules_file` is the only entry point, and it validates in three
layers, reporting every problem of all three in one error:

1. Structural — against :data:`rules/rules.schema.json`: required keys,
   closed ``_cardinality``/``_type`` enumerations, no unknown metadata
   keys, snake_case field names.
2. Coherence — three constraints kept out of the schema on purpose:
    - only ``_type: "object"`` fields may declare child fields;
    - ``_allowed_values``/``_suggested_values`` only on scalar fields;
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
                f"{node.get('_type')!r}; only 'object' fields may have children."
            )
        for vocab_key in ("_allowed_values", "_suggested_values"):
            if vocab_key in node and node.get("_type") == "object":
                problems.append(
                    f"{path}: {vocab_key} on an 'object' field; vocabularies "
                    f"only apply to scalar fields."
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
                f"{path}: _chapter_description but {reason}; only a top-level "
                f"object field becomes a DSW chapter, so anywhere else it "
                f"would be silently ignored (use _description instead)."
            )
        problems.extend(_coherence_problems(node, path, depth + 1))
    return problems


def _standard_slug(standard: str) -> str:
    """The directory a standard's rules files live in, derived from its
    declared name: lowercased, spaces as underscores ("RDA DCS" ->
    "rda_dcs"). The declared name stays the human-readable one that reaches
    READMEs and QC reports; this is only its filesystem form."""
    return standard.lower().replace(" ", "_")


def _layout_problems(path: Path, doc: dict[str, Any]) -> list[str]:
    """Every way the file disagrees with the path it sits at, at once.

    A path names a standard and a version (``<standard>/<version>.json``) and
    the document declares both. Two identifier spaces that drift in silence
    without this check: a stale directory makes provenance name a standard
    nobody selected, and a file copied to a new version filename becomes that
    version, same content, no record.
    """
    problems = []
    slug = _standard_slug(doc["standard"])
    if slug != path.parent.name:
        problems.append(
            f"declares standard {doc['standard']!r} (slug {slug!r}) but sits "
            f"in directory {path.parent.name!r}; the two must agree."
        )
    if doc["version"] != path.stem:
        problems.append(
            f"declares version {doc['version']!r} but is named {path.stem!r}; "
            f"the two must agree."
        )
    return problems


def load_rules_file(path: str | Path) -> dict[str, Any]:
    """Load one ``rules.json`` file, fully validated.

    Returns the parsed document (``standard``/``extends``/``dmp`` and the
    optional ``description``). Raises :class:`RulesFileError` listing every
    problem found — syntax included, so that one exception type covers every
    way a rules file can be wrong and callers need catch nothing else.
    """
    try:
        doc = json.loads(Path(path).read_text())
    except json.JSONDecodeError as err:
        raise RulesFileError(path, [f"invalid JSON: {err}"]) from err
    problems = schema_problems(validator_for(SCHEMA_PATH), doc)
    if not problems and isinstance(doc, dict):
        problems = _coherence_problems(doc.get("dmp", {}), "dmp") + _layout_problems(
            Path(path), doc
        )
    if problems:
        raise RulesFileError(path, problems)
    return doc
