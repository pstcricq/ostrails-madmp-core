"""The Document Template, and what binds it to its KM.

The two are published as separate packages and DSW never checks that they
agree, so the tests that matter here build both from one project and confront
them. Agreement has two halves, and each needs its own: every UUID the
template reads must be one the KM emitted, and must be read from where the KM
hangs it, a reply path being a chain of parenthood, so the right entity sought
under the wrong parent finds nothing. Neither needs an expected output, and
both hold for any project.

The rest is what has a specification: the template body must be Jinja that
parses, it must render to a document that parses, the answer-label table must
translate what the KM stores, and the bundle must name the KM it is allowed to
render.
"""

import itertools
import json
import re
from pathlib import Path

import jinja2
import pytest
import yaml

from dsw.generate_km import build_km_bundle
from dsw.generate_template import (
    FORMATS,
    TEMPLATE_METAMODEL_VERSION,
    build_template_bundle,
    q,
)
from dsw.uuids import (
    answer_uuid,
    chapter_uuid,
    other_answer_uuid,
    other_followup_uuid,
    question_uuid,
)
from project import Project, assemble_project, merge_rules, resolve_pins

ROOT = Path(__file__).parent.parent
GLIDER_CONFIG = ROOT / "configs" / "projects" / "glider.yaml"
STAMP = "2026-01-01T00:00:00.000Z"

# The suggested-vocabulary field whose "Other" sentinel must stay out of AL.
SUGGESTED = ("contact", "affiliation", "affiliation_id", "type")

# A vocabulary that names its own escape value, the way RDA DCS does on every
# identifier type.
OWN_ESCAPE = {
    "id_type": {
        "_cardinality": "1",
        "_type": "string",
        "_suggested_values": ["orcid", "isni", "other"],
    }
}

# An object every standard is entitled to declare: nothing about it is
# required, so the template is handed no key it may emit unconditionally.
ANCHORLESS = {
    "contact": {
        "_cardinality": "1",
        "_type": "object",
        "name": {"_cardinality": "0..1", "_type": "string"},
        "mbox": {"_cardinality": "0..1", "_type": "email"},
    }
}

# A boolean a standard made mandatory. No standard on disk does today, but
# `0..1` -> `1` is a tightening the merge allows, so an extension turns this on
# without a line of code changing.
REQUIRED_BOOLEAN = {
    "is_reused": {"_cardinality": "1", "_type": "boolean"},
    "title": {"_cardinality": "1", "_type": "string"},
}

# A vocabulary spelling its values the way an institution's name is spelt.
# The apostrophe is the character that closes the Jinja literal `AL` holds the
# label in, taking the whole template down with it.
AWKWARD_VOCABULARY = {
    "funder": {
        "_cardinality": "1",
        "_type": "string",
        "_allowed_values": ["Institut d'Optique", 'the "big" one', "back\\slash"],
    }
}

# The same, as a multi-choice: its labels reach the document through a
# different expression, and an array is where a bad one is least visible.
AWKWARD_MULTI = {
    "keyword": {
        "_cardinality": "0..n",
        "_type": "string",
        "_suggested_values": ["Institut d'Optique", 'the "big" one'],
    }
}

# What a researcher can put in a text field and what it costs. Each of these
# ends the JSON string it sits in, or, for the tab, sits inside one as a
# control character JSON does not allow there.
TYPED_BY_HAND = [
    'a "quoted" answer',
    "back\\slash",
    "two\nlines",
    "a\ttab",
    "a\r\nwindows line",
]


@pytest.fixture(scope="module")
def project():
    return assemble_project(GLIDER_CONFIG)


@pytest.fixture(scope="module")
def bundle(project):
    return build_template_bundle(project, created_at=STAMP)


@pytest.fixture(scope="module")
def body(bundle):
    return bundle["files"][0]["content"]


def _uuids_in(text: str) -> set[str]:
    return set(re.findall(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", text))


class _Ctx:
    """The bits of DSW's render context the template reaches for."""

    def __init__(self, **attrs):
        self.__dict__.update(attrs)


# The one list item every list question is given, standing in for a UUID DSW
# would mint at runtime. It is not an entity of the KM.
ITEM = "item-0"


class _AnyValue(str):
    """A reply that equals whatever it is compared against.

    A gate opens only when its stored answer equals its own "Yes" UUID, and a
    test naming each of those would be rebuilding the chains it means to check.
    Agreeing with every comparison opens all of them at once, so a render walks
    the whole tree rather than the part that needs no key to unlock.
    """

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


class _Answered:
    """Replies that answer every path asked of them, whatever it is.

    Which paths a template reads is the template's own business, and a test
    that listed them would be rebuilding the chain logic it is meant to check.
    Saying yes to all of them opens every conditional block without knowing one.

    ``value`` is what every one of them answers, so that a single render puts
    the same string through every route text takes to the document at once.
    """

    def __init__(self, value: str = "answered") -> None:
        self.value = value

    def __contains__(self, path: str) -> bool:
        return True

    def __getitem__(self, path: str) -> _AnyValue:
        return _AnyValue(self.value)


def _render(
    body: str,
    replies,
    chains: list[list[str]] | None = None,
    items=lambda reply: [ITEM],
) -> dict:
    """The template run by Jinja itself, and the document it produced.

    DSW's three reply filters are stubbed: ``reply_path`` joins a chain of
    UUIDs into one key, ``reply_str_value`` hands back the stored reply, and
    ``reply_items`` gives a list question one item to iterate.

    ``chains`` collects every path the template asks ``reply_path`` for, each
    flattened to its UUIDs, a chain built on another chain arriving already
    joined since that is what the filter returned the first time.

    ``items`` overrides the ``reply_items`` stub. The default hands back one
    item that is not an entity of anything, which is what a list question
    stores. A multi-choice stores the UUIDs of the answers that were chosen,
    and the one test that needs a real label to come back out says so.
    """
    env = jinja2.Environment()

    def reply_path(parts) -> str:
        flat = [uuid_ for part in parts for uuid_ in str(part).split(".")]
        if chains is not None:
            chains.append(flat)
        return ".".join(flat)

    env.filters["reply_path"] = reply_path
    env.filters["reply_str_value"] = lambda reply: reply
    env.filters["reply_items"] = items
    ctx = _Ctx(
        project=_Ctx(
            replies=replies,
            createdAt="2026-01-01T00:00:00Z",
            updatedAt="2026-01-02T00:00:00Z",
            uuid="1111",
        ),
        config=_Ctx(clientUrl="https://dsw.example"),
    )
    return json.loads(env.from_string(body).render(ctx=ctx))


def _body_from_rules(tmp_path: Path, dmp: dict) -> str:
    """A template built from a rules tree of one's own, on the real config.

    A shape no standard on disk has today is still a shape a standard may
    have, and the template has to hold for it.
    """
    path = tmp_path / "synthetic" / "1.0.0.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {"standard": "synthetic", "version": "1.0.0", "extends": False, "dmp": dmp}
        )
    )
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    bundle = build_template_bundle(
        Project(config=config, model=merge_rules([path])), created_at=STAMP
    )
    return bundle["files"][0]["content"]


# What binds the template to its KM


def test_every_uuid_the_template_reads_is_an_entity_the_km_emits(project, body):
    """Half of the pair's invariant, the half about identity. They are
    published as two packages and nothing in DSW checks they agree, so a
    UUID drifting on either side is a question whose answer silently never
    reaches the document. The other half, where each of those entities hangs,
    is below."""
    km_entities = {
        event["entityUuid"]
        for event in build_km_bundle(project, created_at=STAMP)["packages"][0]["events"]
    }
    assert _uuids_in(body) - km_entities == set()


def test_the_template_reads_every_question_where_the_km_hangs_it(project, body):
    """The other half, and the one an existing UUID cannot cover: a reply
    path is a chain of parenthood, so reading the right entity from the wrong
    place finds nothing. Both generators build those chains from `dsw.uuids`,
    separately, in code that never meets.

    Rendering is how the chains are collected rather than parsed, DSW handing
    `reply_path` the very list the template assembled, so the filter sees what
    the instance would see. The list item DSW would mint at runtime is not an
    entity, so it drops out and the question beneath a list answers to the
    list itself.

    It holds in both directions. Every chapter and question the KM asks is
    read, so no answer is stranded in a questionnaire nothing exports, and
    nothing is read that the KM never emitted."""
    chains: list[list[str]] = []
    _render(body, _Answered(), chains)
    events = build_km_bundle(project, created_at=STAMP)["packages"][0]["events"]
    parent = {event["entityUuid"]: event["parentUuid"] for event in events}
    asked = {
        event["entityUuid"]
        for event in events
        if event["content"]["eventType"] in ("AddQuestionEvent", "AddChapterEvent")
    }

    read = {entity for chain in chains for entity in chain if entity != ITEM}
    assert asked - read == set(), "the KM asks questions the template never reads"
    assert read - set(parent) == set(), "the template reads what the KM never emitted"

    for chain in chains:
        steps = [entity for entity in chain if entity != ITEM]
        for anchor, entity in itertools.pairwise(steps):
            assert parent[entity] == anchor, (
                f"{entity} is read under {anchor}, the KM hangs it on {parent[entity]}"
            )


def test_the_template_is_allowed_to_render_exactly_its_own_km(project, bundle):
    km = build_km_bundle(project, created_at=STAMP)
    assert bundle["id"] == km["id"]
    assert bundle["templateId"] == km["kmId"]
    allowed = bundle["allowedPackages"][0]
    assert allowed["kmId"] == km["kmId"]
    assert allowed["orgId"] == project.config["organizationId"]


def test_the_answer_table_translates_what_the_km_stores(project, body):
    """DSW stores an answer's UUID and not its label, so AL is how the
    document gets the word back. Every key must therefore be a KM answer."""
    km_entities = {
        event["entityUuid"]
        for event in build_km_bundle(project, created_at=STAMP)["packages"][0]["events"]
    }
    al = body.split("{%- set AL = ", 1)[1].split(" -%}", 1)[0]
    assert _uuids_in(al) <= km_entities


def test_a_vocabulary_that_names_its_own_escape_can_render_that_value(tmp_path):
    """Picking it must put the word in the document. The synthetic "Other"
    shares its UUID and is deliberately absent from AL, so a declared value
    dropped in its favour would make the lookup fall back and a DMP that
    should say `other` say `""` instead."""
    body = _body_from_rules(tmp_path, OWN_ESCAPE)
    asked = f"{chapter_uuid('general')}.{question_uuid(('id_type',))}"
    chosen = answer_uuid(("id_type",), "other")
    assert _render(body, {asked: chosen})["dmp"]["id_type"] == "other"


def test_the_other_sentinel_is_kept_out_of_the_answer_table(body):
    """The lookup falling back to 'other' is what detects the "Other" answer.
    Give it a label and the fallback never fires, and a manually entered value
    is lost."""
    al = body.split("{%- set AL = ", 1)[1].split(" -%}", 1)[0]
    assert other_answer_uuid(SUGGESTED) not in al


# What the template must be


def test_the_body_is_jinja_that_parses(body):
    """The generator writes Jinja and never runs it, so nothing else would
    notice a syntax error before DSW hits it at render time."""
    jinja2.Environment().parse(body)


def test_an_unanswered_project_still_renders_valid_json(body):
    """Nothing answered: every conditional block stays shut, and what is left
    is what the document says about a project a researcher has not opened."""
    document = _render(body, {})
    assert set(document) == {"dmp"}
    assert document["dmp"]["dmp_id"] == {
        "identifier": "https://dsw.example/projects/1111",
        "type": "url",
    }


def test_an_answered_project_still_renders_valid_json(body):
    """The other half, and the half a comma fault needs: every block open.

    An unanswered project renders the conditional keys not at all, so it is
    the one state under which a misplaced comma cannot show. This one answers
    everything the template asks for."""
    document = _render(body, _Answered())
    assert document["dmp"]["title"] == "answered"
    assert document["dmp"]["dataset"][0]["title"] == "answered"


def test_an_object_whose_every_key_is_optional_still_renders_valid_json(tmp_path):
    """A key is emitted with a comma in front of it, so an object closes only
    if something else emitted a key first. Nothing entitles the template to
    that, `cost { type?, unit? }` being an ordinary shape for a standard to
    declare.

    It takes a filled object to fail. Answer nothing and every block stays
    shut, which is why both are asserted here."""
    body = _body_from_rules(tmp_path, ANCHORLESS)
    answered = f"{chapter_uuid('contact')}.{question_uuid(('contact', 'mbox'))}"

    assert _render(body, {answered: "marie@example.org"})["dmp"]["contact"] == {
        "mbox": "marie@example.org"
    }
    assert _render(body, {})["dmp"]["contact"] == {}


# Nothing that reaches the document can end the string it sits in


@pytest.mark.parametrize("typed", TYPED_BY_HAND, ids=lambda t: repr(t))
def test_anything_a_researcher_can_type_still_renders_valid_json(body, typed):
    """The document is assembled as literal JSON text, so a quote, a
    backslash or a newline in a reply ends the string it sits in and takes the
    whole export with it, not one field but the file.

    Answering every path with the same string is what makes one render walk
    every route text takes: a plain value, a vocabulary label, and the free
    text behind a synthetic "Other", the one field in the questionnaire built
    to receive arbitrary input.
    """
    document = _render(body, _Answered(typed))
    assert document["dmp"]["title"] == typed
    assert document["dmp"]["dataset"][0]["dataset_id"]["type"] == typed


def test_a_vocabulary_label_with_an_apostrophe_still_gives_a_template(tmp_path):
    """`AL` holds each label as a Jinja literal, so a label is not only
    data, it is source the generator writes. `Institut d'Optique` closes that
    literal early and the body stops being Jinja at all, which nothing before
    the render would find out."""
    body = _body_from_rules(tmp_path, AWKWARD_VOCABULARY)
    jinja2.Environment().parse(body)

    asked = f"{chapter_uuid('general')}.{question_uuid(('funder',))}"
    for label in AWKWARD_VOCABULARY["funder"]["_allowed_values"]:
        chosen = answer_uuid(("funder",), label)
        assert _render(body, {asked: chosen})["dmp"]["funder"] == label


def test_a_multi_choice_array_carries_its_labels_and_its_free_text_intact(tmp_path):
    """The two expressions the glider project cannot reach: a label emitted
    inside an array, and the free text beside a multi-choice. A multi has no
    "Other" choice to hang a question off, so the manual entry sits next to it
    and is appended to the array. No standard on disk gives a multi-choice a
    synthetic escape today.

    `reply_items` gives back what a multi-choice actually stores, the UUIDs of
    the answers that were chosen, because a label that never comes out of `AL`
    cannot show it arrived whole."""
    body = _body_from_rules(tmp_path, AWKWARD_MULTI)
    labels = AWKWARD_MULTI["keyword"]["_suggested_values"]
    asked = f"{chapter_uuid('general')}.{question_uuid(('keyword',))}"
    typed = f"{chapter_uuid('general')}.{other_followup_uuid(('keyword',))}"
    replies = {
        asked: [answer_uuid(("keyword",), label) for label in labels],
        typed: 'a "manual" keyword',
    }

    document = _render(body, replies, items=lambda reply: reply)
    assert document["dmp"]["keyword"] == [*labels, 'a "manual" keyword']


def test_a_required_boolean_nobody_answered_is_null_and_never_false(tmp_path):
    """A required key is emitted answered or not, so a DMP missing a
    mandatory field says so. A scalar says it with `""`, and a boolean has no
    empty value.

    `false` would not be a silence, it is an answer, and on `is_reused`
    "nobody answered" and "answered no" are not remotely the same claim.
    `null` is what a boolean has instead of an empty string, so the three
    states are three values."""
    body = _body_from_rules(tmp_path, REQUIRED_BOOLEAN)
    asked = f"{chapter_uuid('general')}.{question_uuid(('is_reused',))}"

    unanswered = _render(body, {})["dmp"]
    said_no = _render(body, {asked: answer_uuid(("is_reused",), "no")})["dmp"]
    said_yes = _render(body, {asked: answer_uuid(("is_reused",), "yes")})["dmp"]

    assert unanswered["is_reused"] is None
    assert said_no["is_reused"] is False
    assert said_yes["is_reused"] is True
    assert unanswered["is_reused"] is not said_no["is_reused"]
    # Still emitted at all: the key is what says the field is missing.
    assert "is_reused" in unanswered


def test_an_optional_boolean_is_absent_until_it_is_answered(tmp_path):
    """The other half. Optional keys are conditional, so an unanswered one
    renders nothing at all rather than a null. `dataset.is_reused` is `0..1`
    in RDA DCS, which is every boolean on disk today."""
    optional = dict(
        REQUIRED_BOOLEAN, is_reused={"_cardinality": "0..1", "_type": "boolean"}
    )
    body = _body_from_rules(tmp_path, optional)
    asked = f"{chapter_uuid('general')}.{question_uuid(('is_reused',))}"

    assert "is_reused" not in _render(body, {})["dmp"]
    assert (
        _render(body, {asked: answer_uuid(("is_reused",), "no")})["dmp"]["is_reused"]
        is False
    )


def test_a_uuid_is_quoted_the_same_way_it_always_was():
    """One function writes every Jinja literal, and a UUID must come out of
    it unchanged."""
    assert q(chapter_uuid("general")) == f"'{chapter_uuid('general')}'"


def test_only_an_available_format_becomes_a_dsw_format(bundle):
    """FORMATS is the one place a format is declared, implemented or not, so
    that the README table and the bundle cannot disagree."""
    assert len(bundle["formats"]) == len([f for f in FORMATS if f["available"]])
    assert bundle["formats"][0]["steps"][0]["options"]["extension"] == "json"
    assert TEMPLATE_METAMODEL_VERSION in bundle["readme"]
    assert all(fmt["name"] in bundle["readme"] for fmt in FORMATS)


# What is computed rather than asked


def test_a_computed_field_is_rendered_from_the_project_and_not_from_a_reply(body):
    assert '"created": "{{ ctx.project.createdAt }}"' in body
    assert '"modified": "{{ ctx.project.updatedAt }}"' in body
    assert "{{ ctx.config.clientUrl }}/projects/{{ ctx.project.uuid }}" in body


# The file UUID, derived rather than drawn


def test_two_runs_of_one_project_give_the_same_bundle(project):
    """Including the file UUID, derived from the package id, so that two
    generations of one project differ in nothing a reader can see."""
    assert build_template_bundle(project, created_at=STAMP) == build_template_bundle(
        project, created_at=STAMP
    )


def test_bumping_the_project_version_gives_the_file_a_new_uuid(project, bundle):
    """DSW keys a file's content by this UUID, reuse it across published
    versions and the old content is served for the new package."""
    config = dict(project.config, version="2.0.0")
    other = build_template_bundle(
        Project(config=config, model=project.model), created_at=STAMP
    )
    assert other["files"][0]["uuid"] != bundle["files"][0]["uuid"]
    assert other["id"] == "socib:glider:2.0.0"


def test_a_different_project_gives_the_file_a_different_uuid(project, bundle):
    config = dict(project.config, id="other-project")
    other = build_template_bundle(
        Project(config=config, model=project.model), created_at=STAMP
    )
    assert other["files"][0]["uuid"] != bundle["files"][0]["uuid"]


# The readme states what the template was built from


def test_the_readme_names_the_base_standard_and_its_extensions(bundle):
    assert "RDA_DCS, extended with OSTRAILS" in bundle["readme"]
    assert "- Rules: RDA_DCS 1.0.0, OSTRAILS 1.0.0" in bundle["readme"]


def test_a_project_on_the_base_standard_alone_says_so(project):
    """The coverage line has a branch for it, and no config exercises it."""
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    model = merge_rules(
        resolve_pins([{"rda_dcs": "1.0.0"}], ROOT / "rules" / "standards")
    )
    bundle = build_template_bundle(
        Project(config=config, model=model), created_at=STAMP
    )
    assert (
        "Structured around the `dmp` root object, covering RDA_DCS." in bundle["readme"]
    )
