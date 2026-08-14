"""The typed, merged view of all ``rules/*.json`` files.

``merge_rules()`` loads each file through ``rules.loader``, so every document
is schema-valid before merging, then merges them into a tree of immutable
``Field`` nodes, base standard first.

Every extension is judged against the base, never against what another
extension already imposed. What the extensions require then combines, the
strictest cardinality and the intersection of the vocabularies, so the merged
result does not depend on the order the pins are written in.

Merge semantics, on a field the base already defines an extension may:

- redeclare it identically, which is what repeating a structural parent to
  reach its own new leaf fields looks like
- tighten it: optional to required (``0..1`` -> ``1``, ``0..n`` -> ``1..n``),
  a vocabulary to a subset of itself, an open field closed with a vocabulary
  of its own, or a suggested vocabulary closed over the values it suggests.
  Each tightening is recorded on the field with the standard that imposed it
- never loosen or reshape it: a weaker cardinality, single <-> list, a
  different type, a wider vocabulary, or a closed vocabulary offered back as
  a suggested one are conflicts
- describe what the base left undescribed, or repeat what it says, but not
  say something else, which is a conflict too

Every conflict across all files is collected into one ``RulesConflictError``.
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
# rather than a stripped underscore, the two are separate vocabularies and a
# consumer matches on the aspect.
_VOCABULARY_ASPECTS = {
    "_allowed_values": "allowed_values",
    "_suggested_values": "suggested_values",
}
# Descriptive metadata documents a field, it does not constrain it, so an
# extension may supply what the base left out, or repeat it, but saying
# something else is a conflict.
_DESCRIPTIVE_KEYS = ("_description", "_chapter_description")


def _is_list(cardinality: str) -> bool:
    """Whether a cardinality means the field holds a JSON array.

    Reads _SHAPE rather than repeating which values those are, the same fact
    decides the merge's shape check.
    """
    return _SHAPE[cardinality] == "list"


class RulesSetError(ProblemsError):
    """The set of rules files is ill-formed before any merging is attempted,
    a standard declared twice, or not exactly one base."""


class RulesConflictError(ProblemsError):
    """Two rules files disagree on shared fields in ways the merge semantics
    do not allow.

    No subject, the conflicts are about a set of files.
    """

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
    dotted_path: str  # e.g. "dmp.dataset[].title"
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
    # (standard name, version), base first, each file's declared version.
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
    """A field mid-merge, mutable because tightening rewrites metadata in
    place and appends to the record."""

    # The combined state, what every standard merged so far amounts to.
    meta: dict[str, Any]
    # The declaration every extension is judged against, the introducing
    # standard's own, frozen. Not the same thing as ``meta``.
    base_meta: dict[str, Any]
    origin: str
    # Per metadata key, the standard that wrote the value ``meta`` currently
    # holds. ``origin`` answers a different question, who introduced the
    # field. Kept for every key, not just the tightenable ones, because prose
    # conflicts need it too and nothing records those.
    meta_origin: dict[str, str]
    tightenings: list[Tightening]
    children: dict[str, _Node]


def _new_node(raw: dict[str, Any], origin: str) -> _Node:
    """An interim merge node for a field (and subtree) one file introduced."""
    meta = {k: v for k, v in raw.items() if k.startswith("_")}
    return _Node(
        meta=dict(meta),
        base_meta=meta,
        origin=origin,
        meta_origin=dict.fromkeys(meta, origin),
        tightenings=[],
        children={k: _new_node(v, origin) for k, v in field_children(raw)},
    )


def _ordered_like(reference: list[str], keep: list[str]) -> list[str]:
    """``keep``'s values, in ``reference``'s order."""
    kept = set(keep)
    return [value for value in reference if value in kept]


def _vocabulary_key(meta: dict[str, Any]) -> str | None:
    """Which of the two vocabulary keys a declaration carries, if any.

    At most one, a rules file cannot declare both and the merge never writes a
    second onto a node.
    """
    return next((k for k in _VOCABULARY_ASPECTS if k in meta), None)


def _check_against_base(
    node: _Node, add_key: str, addition: list[str], origin: str, dotted: str
) -> str | None:
    """Whether this extension's vocabulary is a tightening of the base's, and
    what to say if it is not.

    Judged against ``base_meta``, never against what another extension has
    already imposed.
    """
    ref_key = _vocabulary_key(node.base_meta)
    if ref_key is None:
        return None  # an open field: any vocabulary closes it, which tightens
    ref = node.base_meta[ref_key]
    if ref_key == "_allowed_values" and add_key == "_suggested_values":
        return (
            f"{dotted}: {origin} offers _suggested_values where {node.origin} "
            f"closed the vocabulary with _allowed_values, that turns a "
            f"violation into a warning, and an extension may only tighten."
        )
    if set(addition) <= set(ref):
        return None
    outside = sorted(set(addition) - set(ref))
    if ref_key == add_key:
        return (
            f"{dotted}: {origin} widens {add_key} with {outside}, {node.origin} "
            f"declares {ref}, and an extension may only restrict a vocabulary "
            f"to a subset, never widen it."
        )
    return (
        f"{dotted}: {origin} closes the vocabulary on {outside}, which "
        f"{node.origin} does not recommend, closing what is suggested is a "
        f"tightening only over the values the base suggests, here it would "
        f"forbid {sorted(set(ref) - set(addition))}, which it recommends."
    )


def _merge_vocabulary(
    node: _Node,
    raw: dict[str, Any],
    origin: str,
    dotted: str,
    conflicts: list[str],
) -> None:
    """Merge whichever vocabulary an extension declares into the field's.

    Two steps: whether it tightens the base, then what all the extensions
    amount to together, which is an intersection and so does not depend on the
    order they are merged in.

    A field holds at most one vocabulary. The pair is read as a single fact
    with a nature, closed or recommended, and changing that nature is a move
    like any other, closing a recommended vocabulary tightens and the reverse
    is refused.
    """
    add_key = _vocabulary_key(raw)
    if add_key is None:
        return
    addition = list(raw[add_key])

    if problem := _check_against_base(node, add_key, addition, origin, dotted):
        conflicts.append(problem)
        return

    state_key = _vocabulary_key(node.meta)
    if state_key is None:
        _set_vocabulary(node, add_key, addition, origin)
        return

    state, author = node.meta[state_key], node.meta_origin[state_key]
    # The base's order if it has one, so a restriction never reorders what the
    # researcher reads, otherwise the order the first standard to close it used.
    order = node.base_meta.get(_vocabulary_key(node.base_meta) or "", state)

    if state_key == add_key:
        combined = _ordered_like(order, sorted(set(state) & set(addition)))
        if not combined:
            conflicts.append(
                f"{dotted}: {origin} restricts {add_key} to {addition} and "
                f"{author} to {state}, no value satisfies both."
            )
        elif set(combined) != set(state):
            _set_vocabulary(node, add_key, combined, origin)
        # else: nothing this standard says is new, a redeclaration or a subset
        # another extension has already gone below. Not a tightening.
        return

    # One closes, the other recommends. Closing wins, but only over values that
    # are recommended, the rule _check_against_base applies to the base, here
    # between two extensions.
    closed, suggested = (
        (addition, state) if add_key == "_allowed_values" else (state, addition)
    )
    if not set(closed) <= set(suggested):
        closer = origin if add_key == "_allowed_values" else author
        suggester = author if add_key == "_allowed_values" else origin
        conflicts.append(
            f"{dotted}: {closer} closes the vocabulary on "
            f"{sorted(set(closed) - set(suggested))}, which {suggester} does "
            f"not recommend, the two standards disagree on what this field "
            f"may hold."
        )
        return
    if add_key == "_allowed_values":
        # The recommendation is not kept, it has become false.
        node.tightenings.append(
            Tightening(origin, _VOCABULARY_ASPECTS[state_key], list(state), None)
        )
        del node.meta[state_key]
        del node.meta_origin[state_key]
        _set_vocabulary(node, add_key, _ordered_like(order, addition), origin)


def _set_vocabulary(node: _Node, key: str, values: list[str], origin: str) -> None:
    """Record the tightening and write the vocabulary.

    ``before`` is the base's declaration for this key, not the state this
    standard happened to find, so a Tightening says what this standard
    requires beyond the base whatever order the others merged in.
    """
    node.tightenings.append(
        Tightening(origin, _VOCABULARY_ASPECTS[key], node.base_meta.get(key), values)
    )
    node.meta[key] = values
    node.meta_origin[key] = origin


def _merge_meta(
    node: _Node,
    raw: dict[str, Any],
    origin: str,
    dotted: str,
    conflicts: list[str],
) -> None:
    """Merge one extension's metadata onto a field's interim node, applying
    the tighten-only semantics documented at module level."""
    meta, base_meta, wrote = node.meta, node.base_meta, node.meta_origin

    if raw["_type"] != base_meta["_type"]:
        conflicts.append(
            f"{dotted}: _type {base_meta['_type']!r} ({node.origin}) vs "
            f"{raw['_type']!r} ({origin}), a field's type is never negotiable."
        )

    base_card, addition_card = base_meta["_cardinality"], raw["_cardinality"]
    if addition_card != base_card:
        # Against the base's cardinality, not the merged one, so an extension
        # that redeclares what the base says stays a no-op even once another
        # has tightened it. Tightenings then combine, required wins, and a
        # shape has exactly one required form so two can never disagree.
        if _SHAPE[addition_card] != _SHAPE[base_card]:
            conflicts.append(
                f"{dotted}: _cardinality {base_card!r} ({node.origin}) "
                f"vs {addition_card!r} ({origin}) changes the field's shape "
                f"(single value vs list)."
            )
        elif base_card in _REQUIRED:
            conflicts.append(
                f"{dotted}: {origin} loosens _cardinality {base_card!r}, "
                f"required by {node.origin}, to {addition_card!r}, an extension "
                f"may only tighten (optional -> required), never loosen."
            )
        else:
            node.tightenings.append(
                Tightening(origin, "cardinality", base_card, addition_card)
            )
            meta["_cardinality"] = addition_card
            wrote["_cardinality"] = origin

    _merge_vocabulary(node, raw, origin, dotted, conflicts)

    for key in _DESCRIPTIVE_KEYS:
        if key not in raw:
            continue
        if key not in meta:
            meta[key] = raw[key]
            wrote[key] = origin
        elif raw[key] != meta[key]:
            conflicts.append(
                f"{dotted}: {key} differs between {wrote[key]} and {origin}, "
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
    """One interim node and its subtree, frozen into a Field."""
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
    """Load, validate, and merge every rules file into one ``Model``.

    Every path must be a real ``<standard>/<version>.json``, the loader checks
    placement. The base standard is found by its own ``extends: false``
    declaration, so input order does not matter, and the extensions keep the
    order given in ``Model.extension_standards``.

    Raises whatever the rules loader raises for a malformed file,
    ``RulesSetError`` for an ill-formed set of files (no base, several bases,
    duplicate standard names), and ``RulesConflictError`` if extensions
    contradict the merge semantics. Each carries every problem of its phase.
    """
    return _build_model([(str(p), load_rules_file(p)) for p in rules_paths])


def _set_problems(docs: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Everything wrong with the set of files before any merging, a standard
    declared twice or not exactly one base."""
    problems = []
    seen: dict[str, str] = {}
    for path, doc in docs:
        standard = doc["standard"]
        if standard in seen:
            problems.append(
                f'{path!r} declares "standard": {standard!r}, already declared '
                f"by {seen[standard]!r}, standard names must be unique."
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

    Two phases, each complete: whether the set of files is well-formed, then
    whether they merge. Every problem of a phase is collected before it
    raises.
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

    # The document's own declaration, not the filename, the loader keeps the
    # two in agreement.
    version_of = {doc["standard"]: doc["version"] for _, doc in docs}
    ordered = (base["standard"], *(doc["standard"] for doc in extensions))
    return Model(
        base_standard=base["standard"],
        extension_standards=tuple(doc["standard"] for doc in extensions),
        fields=tuple(_freeze(k, node, (), "dmp") for k, node in merged.items()),
        standard_versions=tuple((s, version_of[s]) for s in ordered),
    )
