"""The KM bundle, checked for what is specified rather than against a copy.

There is no expected bundle to compare to: a KM is whatever the rules of a
project say, so freezing one project's output would record this generator
rather than judge it. What can be judged is what has a specification, the
DSW metamodel, the UUID convention and the mapping stated in ``field_kind``,
plus one invariant that holds for any project whatsoever: an event may not
reference a parent nobody emitted.
"""

from pathlib import Path

import pytest

from dsw.common import field_kind, standard_label
from dsw.generate_km import (
    METAMODEL_VERSION,
    VALUE_TYPE_MAP,
    build_km_bundle,
    humanize,
)
from dsw.uuids import (
    chapter_uuid,
    gate_uuid,
    gate_yes_uuid,
    list_item_value_uuid,
    other_answer_uuid,
    other_followup_uuid,
    question_uuid,
)
from project import assemble_project

ROOT = Path(__file__).parent.parent
GLIDER_CONFIG = ROOT / "configs" / "projects" / "glider.yaml"
NIL = "00000000-0000-0000-0000-000000000000"

# Paths chosen for the kind of entity they become, not for their content.
GATED = ("dataset", "distribution", "host")
SUGGESTED = ("contact", "affiliation", "affiliation_id", "type")
MULTI_VALUE = ("dataset", "data_quality_assurance")
# Two vocabularies that spell the escape value themselves: RDA DCS writes it
# ``other``, DataCite writes it ``Other``.
OWN_OTHER = ("dataset", "creator", "creator_id", "type")
OWN_OTHER_MULTI = ("contributor", "role")


@pytest.fixture(scope="module")
def project():
    return assemble_project(GLIDER_CONFIG)


@pytest.fixture(scope="module")
def events(project):
    return build_km_bundle(project, created_at="2026-01-01T00:00:00.000Z")["packages"][
        0
    ]["events"]


@pytest.fixture(scope="module")
def by_entity(events):
    return {e["entityUuid"]: e for e in events}


def _children_of(events, parent_uuid):
    return [e for e in events if e["parentUuid"] == parent_uuid]


# The bundle DSW is handed


def test_the_bundle_names_the_project_and_the_metamodel(project, events):
    bundle = build_km_bundle(project, created_at="2026-01-01T00:00:00.000Z")
    package = bundle["packages"][0]
    assert bundle["id"] == f"socib:glider:{project.config['version']}"
    assert bundle["kmId"] == "glider"
    assert bundle["metamodelVersion"] == METAMODEL_VERSION
    assert package["id"] == bundle["id"]
    assert package["phase"] == "ReleasedKnowledgeModelPackagePhase"
    assert package["events"] == events


def test_the_description_is_plain_text(project):
    """The readme is Markdown and the description is not, DSW rendering them
    differently though both are written once in the config."""
    package = build_km_bundle(project)["packages"][0]
    assert "**" not in package["description"] and "](" not in package["description"]
    assert "**" in package["readme"]


def test_two_runs_of_one_project_are_the_same_bundle(project):
    """Everything is derived from the project except the timestamp, which is
    why the timestamp is injectable."""
    stamp = "2026-01-01T00:00:00.000Z"
    assert build_km_bundle(project, created_at=stamp) == build_km_bundle(
        project, created_at=stamp
    )


def test_every_event_carries_the_fields_its_metamodel_defines_and_no_others(events):
    """The one thing about this bundle that is somebody else's specification.

    Each ``Add*EventContent`` of ``kmp_schema_v20.json`` is
    ``additionalProperties: false``, so a field the metamodel does not define
    is not a field this may send. A bundle that is out of schema publishes
    today and is a bundle nobody else can validate.

    Read off the schema and written out here rather than validated against the
    file itself, which would mean vendoring a hundred kilobytes of somebody
    else's JSON. The fields this generator emits are two dozen names that say,
    in one place, what a KM event is.
    """
    metamodel = {
        "AddKnowledgeModelEvent": {"annotations", "eventType"},
        "AddPhaseEvent": {"annotations", "description", "eventType", "title"},
        "AddTagEvent": {"annotations", "color", "description", "eventType", "name"},
        "AddChapterEvent": {"annotations", "eventType", "text", "title"},
        "AddAnswerEvent": {
            "advice",
            "annotations",
            "eventType",
            "label",
            "metricMeasures",
        },
        "AddChoiceEvent": {"annotations", "eventType", "label"},
    }
    question = {
        "annotations",
        "eventType",
        "questionType",
        "requiredPhaseUuid",
        "tagUuids",
        "text",
        "title",
    }
    questions = {
        "ValueQuestion": question | {"validations", "valueType"},
        "OptionsQuestion": question,
        "ListQuestion": question,
        "MultiChoiceQuestion": question,
    }

    for event in events:
        assert set(event) == {
            "uuid",
            "entityUuid",
            "parentUuid",
            "createdAt",
            "content",
        }
        content = event["content"]
        kind = content["eventType"]
        expected = (
            questions[content["questionType"]]
            if kind == "AddQuestionEvent"
            else metamodel[kind]
        )
        assert set(content) == expected, f"{kind} {content.get('questionType') or ''}"


# The invariant that holds for any project


def test_no_event_references_a_parent_nobody_emitted(events):
    """DSW applies the events in order onto an empty model, so a parent that
    arrives later, or never, is an entity that silently vanishes."""
    emitted = {NIL}
    for event in events:
        assert event["parentUuid"] in emitted, event["content"]
        emitted.add(event["entityUuid"])


def test_every_entity_is_emitted_once(events):
    uuids = [e["entityUuid"] for e in events]
    assert len(set(uuids)) == len(uuids)


def test_every_type_asked_as_a_value_has_a_dsw_value_type(project):
    """The one crossing between the rules vocabulary and this generator, a
    type added to a standard without a mapping here fails at generation. Only
    the kinds that become a ValueQuestion need one, a boolean is asked as a
    Yes/No OptionsQuestion and a vocabulary as its answers."""
    computed = {"dmp_id", "created", "modified"}
    missing = {
        field.type
        for field in project.model.walk()
        if field_kind(field, computed) in ("value", "value_multi")
        and field.type not in VALUE_TYPE_MAP
    }
    assert missing == set()


# The chapters


def test_the_general_chapter_comes_first_and_the_others_follow_in_order(events):
    chapters = [e for e in events if e["content"]["eventType"] == "AddChapterEvent"]
    titles = [e["content"]["title"] for e in chapters]
    assert titles[0] == "1. DMP General Information"
    assert [t.split(".")[0] for t in titles] == [
        str(i) for i in range(1, len(titles) + 1)
    ]


def test_every_top_level_object_becomes_a_chapter_unless_it_is_computed(
    project, by_entity
):
    """``dmp_id`` is the case that matters, a top-level object and computed, so
    it gets no chapter rather than an empty one."""
    computed = {"dmp_id", "created", "modified"}
    for field in project.model.fields:
        if field.type != "object":
            continue
        if field_kind(field, computed) == "computed":
            assert chapter_uuid(field.name) not in by_entity
            continue
        assert by_entity[chapter_uuid(field.name)]["content"]["title"].endswith(
            humanize(field.name)
        )


def test_a_computed_field_becomes_neither_chapter_nor_question(project, by_entity):
    """``dmp_id`` and, under auto_timestamps, ``created``/``modified`` are filled
    by the template from the render context, so asking them would be asking
    the researcher for something already known."""
    for name in ("dmp_id", "created", "modified"):
        assert question_uuid((name,)) not in by_entity
        assert chapter_uuid(name) not in by_entity


def test_the_readme_lists_every_chapter(project, events):
    readme = build_km_bundle(project)["packages"][0]["readme"]
    chapters = [e for e in events if e["content"]["eventType"] == "AddChapterEvent"]
    rows = [line for line in readme.splitlines() if line.startswith("| ")]
    assert len(rows) == len(chapters) + 1  # + the header row


# The questions, kind by kind


def test_an_optional_object_is_asked_behind_a_yes_no_gate(events, by_entity):
    """Its children hang under the Yes answer, so an optional block asks
    nothing at all until it is opted into."""
    gate = by_entity[gate_uuid(GATED)]
    assert gate["content"]["questionType"] == "OptionsQuestion"
    labels = [e["content"]["label"] for e in _children_of(events, gate_uuid(GATED))]
    assert labels == ["Yes", "No"]
    assert _children_of(events, gate_yes_uuid(GATED)) != []


def test_a_suggested_vocabulary_gets_an_other_answer_and_a_follow_up(events, by_entity):
    """A suggested vocabulary admits values it does not list, so one that
    does not name an escape of its own is given one, an "Other" answer
    opening a free-text follow-up."""
    answers = _children_of(events, question_uuid(SUGGESTED))
    labels = [a["content"]["label"] for a in answers]
    assert labels == ["ror", "grid", "isni", "Other"]
    follow_up = by_entity[other_followup_uuid(SUGGESTED)]
    assert follow_up["parentUuid"] == other_answer_uuid(SUGGESTED)
    assert follow_up["content"]["valueType"] == "StringQuestionValueType"


def test_a_vocabulary_that_names_its_own_escape_keeps_it_and_gets_no_second(
    events, by_entity
):
    """``other`` is a value of the RDA DCS vocabulary, it says the identifier
    scheme is outside the list and the standard offers no field to say which.
    So a field that names one is asked like a closed vocabulary, its own value
    offered in its own spelling and nothing beside it. A second escape would
    take the declared value's place, and its UUID with it."""
    labels = [
        a["content"]["label"] for a in _children_of(events, question_uuid(OWN_OTHER))
    ]
    assert labels == ["orcid", "isni", "openid", "other"]
    assert other_followup_uuid(OWN_OTHER) not in by_entity


def test_a_multi_choice_vocabulary_keeps_the_escape_it_names(events, by_entity):
    """DataCite ends contributorType with ``Other``, and a multi-choice
    question has no answer to hang a follow-up off. Dropping it would leave a
    required controlled vocabulary missing one of its own values, reachable
    only by typing it into the free-text question next door."""
    labels = [
        a["content"]["label"]
        for a in _children_of(events, question_uuid(OWN_OTHER_MULTI))
    ]
    assert labels[-1] == "Other"
    assert other_followup_uuid(OWN_OTHER_MULTI) not in by_entity


def test_a_repeated_scalar_becomes_a_list_of_one_value_question(events, by_entity):
    """DSW has no way to ask for several of one value, so the cardinality
    becomes a ListQuestion with a single item template."""
    question = by_entity[question_uuid(MULTI_VALUE)]
    assert question["content"]["questionType"] == "ListQuestion"
    item = by_entity[list_item_value_uuid(MULTI_VALUE)]
    assert item["parentUuid"] == question_uuid(MULTI_VALUE)
    assert item["content"]["questionType"] == "ValueQuestion"


def test_every_question_carries_the_path_it_fills(project, by_entity):
    """The annotation is how a later consumer maps an answer back to a rules
    field."""
    for field in project.model.walk():
        event = by_entity.get(question_uuid(field.path))
        if event is None:
            continue
        assert event["content"]["annotations"][0] == {
            "key": "rules_path",
            "value": ".".join(field.path),
        }


def test_no_question_is_asked_without_saying_what_it_fills(events):
    """The one above walks the fields and looks each one's question up, so a
    question it has no field to look up is a question it never sees. The item
    template of a repeated scalar is one of those, and it is exactly the
    entity a reply is stored against, so a question with no annotation is an
    answer no consumer could place.

    A chapter may have no path, the general one being ours rather than a
    standard's. A question may not, it was asked because a rules field asked
    for it."""
    for event in events:
        if event["content"]["eventType"] != "AddQuestionEvent":
            continue
        keys = [a["key"] for a in event["content"]["annotations"]]
        assert "rules_path" in keys, event["content"]["title"]


# Tags and phases, the two things a researcher navigates by


def test_one_tag_per_standard_shown_the_way_a_standard_is_shown(project, events):
    """Beside the three fixed tags, which are upper case too, a standard is
    written ``rda_dcs`` in code and shown ``RDA_DCS``."""
    tags = [e for e in events if e["content"]["eventType"] == "AddTagEvent"]
    names = [t["content"]["name"] for t in tags]
    assert names == [
        "REQUIRED",
        "OPTIONAL",
        "CONTROLLED VOCABULARY",
        *(standard_label(s) for s in project.model.standards),
    ]


def test_only_required_fields_join_the_required_phase(project, by_entity):
    computed = {"dmp_id", "created", "modified"}
    for field in project.model.walk():
        event = by_entity.get(question_uuid(field.path))
        if event is None or field_kind(field, computed) == "computed":
            continue
        if "requiredPhaseUuid" not in event["content"]:
            continue
        assert (event["content"]["requiredPhaseUuid"] is not None) == field.is_required
