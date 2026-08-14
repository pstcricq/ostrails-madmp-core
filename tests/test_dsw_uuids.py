"""The frozen half of the UUID convention, held against what is published.

These are not tests of an algorithm, ``uuid5`` needs none. They are the guard
on values that may never change: every UUID below appears verbatim in an
artifact already built and published to DS Wizard, so a change to the
namespace or to any part string turns this file red instead of breaking every
reference in every published package.

Each value was verified on 31/07/2026 against the glider KM bundle as it was
then generated.
"""

import uuid

import pytest

from dsw.uuids import (
    NAMESPACE,
    answer_uuid,
    chapter_uuid,
    gate_no_uuid,
    gate_uuid,
    gate_yes_uuid,
    list_item_value_uuid,
    other_answer_uuid,
    other_followup_uuid,
    question_uuid,
    u,
)

# A path per entity kind, chosen because the published KM contains that kind's
# UUID for that very path.
GATED = ("dataset", "distribution", "host")
SUGGESTED = ("contact", "affiliation", "affiliation_id", "type")
ACCESS = ("dataset", "distribution", "data_access")
QUALITY = ("dataset", "data_quality_assurance")

PUBLISHED = [
    (chapter_uuid("dataset"), "73b95adf-5c95-5cc5-863b-cd8e1e52bdca"),
    (question_uuid(("alternate_identifier",)), "16b224c2-88ad-5be5-8018-0618671980a1"),
    (answer_uuid(ACCESS, "open"), "3849ea1c-53f3-537c-b3e8-24058ebe2c2b"),
    (other_answer_uuid(SUGGESTED), "1e9e14f1-7732-5bf4-9e18-82fa76c9944e"),
    (other_followup_uuid(SUGGESTED), "362df3a0-42dd-5bcd-8ac2-cbd23c1711b1"),
    (list_item_value_uuid(QUALITY), "d0a4d863-4f56-5361-9800-2c6c873eb0d3"),
    (gate_uuid(GATED), "508156e9-39c3-5229-9964-973b299a4b33"),
    (gate_yes_uuid(GATED), "507995df-3bec-59c6-be59-e2061a24ae03"),
    (gate_no_uuid(GATED), "02e5ce05-a749-5bfa-be34-c7166e5f8c2d"),
]


# What is published, and may not move


@pytest.mark.parametrize("derived, published", PUBLISHED)
def test_every_kind_derives_what_is_already_published(derived, published):
    assert derived == published


def test_the_namespace_is_the_nil_uuid():
    """Named on its own, every value above hangs off it, so it is the single
    change that would move all nine at once."""
    assert NAMESPACE == uuid.UUID("00000000-0000-0000-0000-000000000000")


# What the convention guarantees


def test_one_path_gives_every_kind_a_distinct_identity():
    """A field becomes several DSW entities at once, a gate question, its
    two answers, the question itself. They share a path and must not share a
    UUID."""
    derived = [
        question_uuid(GATED),
        gate_uuid(GATED),
        gate_yes_uuid(GATED),
        gate_no_uuid(GATED),
        other_followup_uuid(GATED),
        list_item_value_uuid(GATED),
        chapter_uuid("host"),
    ]
    assert len(set(derived)) == len(derived)


def test_the_path_is_what_distinguishes_two_questions():
    """Same field name under two parents is two questions, not one."""
    assert question_uuid(("dataset", "title")) != question_uuid(("project", "title"))


# What it does not guarantee, and that is frozen too


def test_the_other_answer_is_the_answer_named_other():
    """A vocabulary listing the word literally hands its answer the identity
    of the synthetic "Other". The two can no longer be asked at once, since
    `needs_a_synthetic_escape` withholds the synthetic answer from a
    vocabulary naming an escape of its own, but the shared identity is
    frozen."""
    assert other_answer_uuid(SUGGESTED) == answer_uuid(SUGGESTED, "other")


def test_the_parts_are_joined_and_not_escaped():
    """`u` joins on "::", so a name containing the separator would collide
    with a deeper path. Field names are dmp keys, and none carries it."""
    assert u("dataset::title") == u("dataset", "title")
