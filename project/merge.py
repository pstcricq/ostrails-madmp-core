"""The typed, merged view of all ``rules/*.json`` files: the one artifact
every consumer (DSW generation, QC) reads.

:func:`merge_rules` loads each file through :mod:`rules.loader` (so every
document is schema-valid before merging), then strictly merges them into a
tree of immutable :class:`Field` nodes, base standard first.

Merge semantics — on a field the base already defines, an extension may:

- redeclare it identically (the usual case: repeating a structural parent
  purely to reach its own new leaf fields underneath);
- **tighten** it — optional to required (``0..1`` -> ``1``, ``0..n`` ->
  ``1..n``), a vocabulary to a subset of itself, or an open field closed
  with a vocabulary of its own. Each tightening is recorded on the field
  (:class:`Tightening`) with the standard that imposed it;
- never **loosen** or reshape it: a weaker cardinality, single <-> list, a
  different type, or a wider vocabulary are conflicts;
- describe what the base left undescribed, or repeat what it says — but not
  say something else, which is a conflict too. Prose constrains nothing, and
  is still nobody's to overwrite in silence.

The asymmetry is the point, and doc.md ("La fusion tighten-only") says
why. Every conflict across all files is collected into one
:class:`RulesConflictError`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rules import field_children, load_rules_file
from utils.errors import ProblemsError

_SHAPE = {"1": "single", "0..1": "single", "1..n": "list", "0..n": "list"}
_REQUIRED = {"1", "1..n"}
# Metadata key -> the aspect name a Tightening records it under. A mapping
# rather than stripping the underscore: the two are different vocabularies,
# and a consumer matching on aspect must not break because a metadata key
# was renamed.
_VOCABULARY_ASPECTS = {
    "_allowed_values": "allowed_values",
    "_suggested_values": "suggested_values",
}
# Descriptive metadata documents a field, it does not constrain it, so an
# extension may supply what the base left out — and may repeat what the base
# says, which is what redeclaring a structural parent looks like. Saying
# something *else* is a conflict rather than a silent drop: prose an author
# wrote and nothing carries is the fault `_chapter_description` already has a
# coherence check for.
_DESCRIPTIVE_KEYS = ("_description", "_chapter_description")


def _is_list(cardinality: str) -> bool:
    """Whether a cardinality means the field holds a JSON array. Reads
    _SHAPE rather than repeating which values those are: the same fact
    decides the merge's shape check, so it is written once."""
    return _SHAPE[cardinality] == "list"


class RulesSetError(ProblemsError):
    """The set of rules files is ill-formed before any merging is attempted:
    a standard declared twice, or not exactly one base."""


class RulesConflictError(ProblemsError):
    """Two rules files disagree on shared fields in ways the merge semantics
    don't allow. No subject: the conflicts are about a *set* of files."""

    noun = "rules conflict"


@dataclass(frozen=True)
class Tightening:
    """One restriction an extension imposed on a field the base standard
    left weaker: the aspect it tightened, and the before/after values."""

    standard: str
    aspect: Literal["cardinality", "allowed_values", "suggested_values"]
    before: Any
    after: Any


@dataclass(frozen=True)
class Field:
    """One merged DMP field: its constraints, its provenance, its children."""

    name: str
    path: tuple[str, ...]  # from the dmp root, e.g. ("dataset", "title")
    dotted_path: str  # QC convention, e.g. "dmp.dataset[].title"
    cardinality: str
    type: str
    origin: str  # the standard that introduced this field
    description: str | None = None
    chapter_description: str | None = None
    allowed_values: tuple[str, ...] | None = None
    suggested_values: tuple[str, ...] | None = None
    tightenings: tuple[Tightening, ...] = ()
    children: tuple[Field, ...] = ()

    @property
    def is_list(self) -> bool:
        return _is_list(self.cardinality)

    @property
    def is_required(self) -> bool:
        return self.cardinality in _REQUIRED

    def walk(self) -> Iterator[Field]:
        """This field, then every descendant, depth-first."""
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True)
class Model:
    """The merged rules of every standard, base first."""

    base_standard: str
    extension_standards: tuple[str, ...]
    fields: tuple[Field, ...]  # top-level dmp fields
    # (standard name, version), base first — each file's declared version.
    # The rules provenance stamped into generated artifacts and QC reports.
    standard_versions: tuple[tuple[str, str], ...]

    @property
    def standards(self) -> tuple[str, ...]:
        return (self.base_standard, *self.extension_standards)

    def walk(self) -> Iterator[Field]:
        """Every field of the merged tree, depth-first."""
        for field in self.fields:
            yield from field.walk()


# Merging (over mutable interim nodes, frozen into Field at the end)


@dataclass
class _Node:
    """A field mid-merge: mutable, because tightening rewrites metadata in
    place and appends to the record. `children` holds more of the same, which
    is the one thing the dict this replaced could not say out loud."""

    meta: dict[str, Any]
    origin: str
    tightenings: list[Tightening]
    children: dict[str, _Node]


def _new_node(raw: dict[str, Any], origin: str) -> _Node:
    """An interim merge node for a field (and subtree) one file introduced."""
    return _Node(
        meta={k: v for k, v in raw.items() if k.startswith("_")},
        origin=origin,
        tightenings=[],
        children={k: _new_node(v, origin) for k, v in field_children(raw)},
    )


def _merge_vocabulary(
    node: _Node,
    raw: dict[str, Any],
    key: str,
    origin: str,
    dotted: str,
    conflicts: list[str],
) -> None:
    addition = raw.get(key)
    if addition is None:
        return
    base = node.meta.get(key)
    if addition == base:
        return
    if base is not None and not set(addition) <= set(base):
        widened = sorted(set(addition) - set(base))
        conflicts.append(
            f"{dotted}: {origin} widens {key} with {widened}; an extension "
            f"may only restrict a vocabulary to a subset, never widen it."
        )
        return
    node.tightenings.append(
        Tightening(origin, _VOCABULARY_ASPECTS[key], base, list(addition))
    )
    node.meta[key] = addition


def _merge_meta(
    node: _Node,
    raw: dict[str, Any],
    origin: str,
    dotted: str,
    conflicts: list[str],
) -> None:
    """Merge one extension's metadata onto a field's interim node,
    applying the tighten-only semantics documented at module level."""
    meta = node.meta

    if raw["_type"] != meta["_type"]:
        conflicts.append(
            f"{dotted}: _type {meta['_type']!r} ({node.origin}) vs "
            f"{raw['_type']!r} ({origin}); a field's type is never negotiable."
        )

    base_card, addition_card = meta["_cardinality"], raw["_cardinality"]
    if addition_card != base_card:
        if _SHAPE[addition_card] != _SHAPE[base_card]:
            conflicts.append(
                f"{dotted}: _cardinality {base_card!r} ({node.origin}) vs "
                f"{addition_card!r} ({origin}) changes the field's shape "
                f"(single value vs list)."
            )
        elif base_card in _REQUIRED:
            conflicts.append(
                f"{dotted}: {origin} loosens _cardinality {base_card!r} to "
                f"{addition_card!r}; an extension may only tighten "
                f"(optional -> required), never loosen."
            )
        else:
            node.tightenings.append(
                Tightening(origin, "cardinality", base_card, addition_card)
            )
            meta["_cardinality"] = addition_card

    for key in _VOCABULARY_ASPECTS:
        _merge_vocabulary(node, raw, key, origin, dotted, conflicts)

    for key in _DESCRIPTIVE_KEYS:
        if key not in raw:
            continue
        if key not in meta:
            meta[key] = raw[key]
        elif raw[key] != meta[key]:
            conflicts.append(
                f"{dotted}: {key} differs between {node.origin} and {origin}; "
                f"an extension may describe a field the base left undescribed, "
                f"or repeat what it says, but not replace it."
            )


def _merge_children(
    merged: dict[str, _Node],
    raw_children: dict[str, dict],
    origin: str,
    prefix: str,
    conflicts: list[str],
) -> None:
    for key, raw in raw_children.items():
        dotted = f"{prefix}.{key}"
        if key in merged:
            node = merged[key]
            _merge_meta(node, raw, origin, dotted, conflicts)
            _merge_children(
                node.children, dict(field_children(raw)), origin, dotted, conflicts
            )
        else:
            merged[key] = _new_node(raw, origin)


def _freeze(
    name: str, node: dict[str, Any], parent_path: tuple[str, ...], parent_dotted: str
) -> Field:
    meta = node.meta
    path = parent_path + (name,)
    is_list = _is_list(meta["_cardinality"])
    dotted = f"{parent_dotted}.{name}[]" if is_list else f"{parent_dotted}.{name}"

    def _values(key: str) -> tuple[str, ...] | None:
        return tuple(meta[key]) if key in meta else None

    return Field(
        name=name,
        path=path,
        dotted_path=dotted,
        cardinality=meta["_cardinality"],
        type=meta["_type"],
        origin=node.origin,
        description=meta.get("_description"),
        chapter_description=meta.get("_chapter_description"),
        allowed_values=_values("_allowed_values"),
        suggested_values=_values("_suggested_values"),
        tightenings=tuple(node.tightenings),
        children=tuple(
            _freeze(k, child, path, dotted) for k, child in node.children.items()
        ),
    )


def merge_rules(rules_paths: list[str | Path]) -> Model:
    """Load, validate, and merge every rules file into one :class:`Model`.

    Which files, it does not decide: turning a project's pinned versions into
    this list of paths belongs to whoever holds the project data, not here —
    ``rules/`` has no notion of a project. But every path must be a real
    ``<standard>/<version>.json``, because :func:`rules.loader.load_rules_file`
    checks placement; this seam is no longer layout-agnostic.

    Input order doesn't matter: the base standard is found by its own
    ``extends: false`` declaration; extensions merge in input order.

    Raises whatever :func:`rules.loader.load_rules_file` raises for a
    malformed file, :class:`RulesSetError` for an ill-formed *set* of files
    (no base, several bases, duplicate standard names), and
    :class:`RulesConflictError` if extensions contradict the merge semantics.
    Each carries every problem of its own phase.
    """
    return _build_model([(str(p), load_rules_file(p)) for p in rules_paths])


def _set_problems(docs: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Everything wrong with the *set* of files, before any merging: a standard
    declared twice, or not exactly one base. Both are visible from one pass, so
    both are reported from one pass."""
    problems = []
    seen: dict[str, str] = {}
    for path, doc in docs:
        standard = doc["standard"]
        if standard in seen:
            problems.append(
                f'{path!r} declares "standard": {standard!r}, already declared '
                f"by {seen[standard]!r}; standard names must be unique."
            )
        else:
            seen[standard] = path

    bases = [path for path, doc in docs if doc["extends"] is False]
    if len(bases) != 1:
        problems.append(
            f'rules files must contain exactly one base standard ("extends": '
            f"false), found {len(bases)} among {sorted(path for path, _ in docs)}."
        )
    return problems


def _build_model(docs: list[tuple[str, dict[str, Any]]]) -> Model:
    """Merge already-loaded, already-validated rules documents.

    Two phases, each complete: is this set of files well-formed, then do they
    merge. The order is forced — there is nothing to merge onto without a base
    — but inside each phase every problem is collected.
    """
    if problems := _set_problems(docs):
        raise RulesSetError(problems)

    base = next(doc for _, doc in docs if doc["extends"] is False)
    extensions = [doc for _, doc in docs if doc["extends"] is True]

    merged: dict[str, _Node] = {
        key: _new_node(raw, base["standard"])
        for key, raw in field_children(base["dmp"])
    }
    conflicts: list[str] = []
    for doc in extensions:
        _merge_children(
            merged, dict(field_children(doc["dmp"])), doc["standard"], "dmp", conflicts
        )
    if conflicts:
        raise RulesConflictError(conflicts)

    # The document's own declaration, not the filename. The loader is what
    # keeps the two in agreement, on every file of the tree.
    version_of = {doc["standard"]: doc["version"] for _, doc in docs}
    ordered = (base["standard"], *(doc["standard"] for doc in extensions))
    return Model(
        base_standard=base["standard"],
        extension_standards=tuple(doc["standard"] for doc in extensions),
        fields=tuple(_freeze(k, node, (), "dmp") for k, node in merged.items()),
        standard_versions=tuple((s, version_of[s]) for s in ordered),
    )
