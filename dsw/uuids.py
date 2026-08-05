"""The rules-field-path -> DSW-entity-UUID convention.

Every DSW entity — chapter, question, answer, gate — takes its UUID from
``uuid5`` over the path of the field it was generated for. Two generators
therefore compute identical UUIDs for the same logical entity without sharing
a lookup table, which is what lets a Document Template reference a Knowledge
Model's questions.

**Frozen.** The namespace and every part string below are the identity of every
entity in every KM and template already published in DSW. Change one and every
derived UUID changes, breaking every reference in every published package. The
tests hold the derived values for exactly this reason.

This module knows nothing but the standard library and the shape of a field
path: no config, no model, no DSW payload. See ``doc.md`` ("La convention
d'UUID déterministe") for what the convention buys and what it costs.
"""

from __future__ import annotations

import uuid

FieldPath = tuple[str, ...]

# NEVER change this value, nor any of the part strings passed to u() below:
# every derived UUID would change, breaking every reference in every KM and
# template already published in DSW.
NAMESPACE = uuid.UUID("00000000-0000-0000-0000-000000000000")


def u(*parts: str) -> str:
    """Derive a deterministic entity UUID from a sequence of name parts."""
    return str(uuid.uuid5(NAMESPACE, "::".join(parts)))


def question_uuid(path: FieldPath) -> str:
    """The question entity for a field."""
    return u(*path, "question")


def answer_uuid(path: FieldPath, value: str) -> str:
    """One answer/choice entity of an options question."""
    return u(*path, "answer", value)


def other_answer_uuid(path: FieldPath) -> str:
    """The "Other" answer entity of a suggested-values question.

    By construction this is :func:`answer_uuid` of the value ``"other"``: a
    vocabulary listing that word literally would give its answer the same
    identity as the synthetic one. No standard does today, and the convention
    is frozen, so this is a hazard to know rather than a bug to fix.
    """
    return u(*path, "answer", "other")


def other_followup_uuid(path: FieldPath) -> str:
    """The free-text follow-up question shown after "Other"."""
    return u(*path, "other-followup", "question")


def list_item_value_uuid(path: FieldPath) -> str:
    """The single item-template ValueQuestion of a "value_multi" field's
    synthetic ListQuestion."""
    return u(*path, "item-value", "question")


def gate_uuid(path: FieldPath) -> str:
    """The Yes/No gate question for a 0..1 object field."""
    return u(*path, "has-question")


def gate_yes_uuid(path: FieldPath) -> str:
    """Its Yes answer — the one that opens the object's own questions."""
    return u(*path, "has-answer", "yes")


def gate_no_uuid(path: FieldPath) -> str:
    """Its No answer, which leads nowhere and is the point of the gate."""
    return u(*path, "has-answer", "no")


def chapter_uuid(key: str) -> str:
    """A top-level chapter entity, keyed by its dmp field."""
    return u("chapter", key)
