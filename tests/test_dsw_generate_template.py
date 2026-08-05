"""The Document Template, and the one thing that binds it to its KM.

A template is only useful if every UUID it reads is a UUID the KM emitted:
they are published as two packages and DSW never checks that they agree. The
test that matters here builds both from the same project and confronts them —
it needs no expected output and holds for any project.

The rest is what has a specification: the template body must be Jinja that
parses, the answer-label table must translate what the KM stores, and the
bundle must name the KM it is allowed to render.
"""

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
)
from dsw.uuids import chapter_uuid, other_answer_uuid, question_uuid
from project import Project, assemble_project, merge_rules, resolve_pins

ROOT = Path(__file__).parent.parent
GLIDER_CONFIG = ROOT / "configs" / "projects" / "glider.yaml"
STAMP = "2026-01-01T00:00:00.000Z"

# The suggested-vocabulary field whose "Other" sentinel must stay out of AL.
SUGGESTED = ("contact", "affiliation", "affiliation_id", "type")

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


class _Answered:
    """Replies that answer every path asked of them, whatever it is.

    Which paths a template reads is the template's own business, and a test
    that listed them would be rebuilding the chain logic it is meant to check.
    Saying yes to all of them opens every conditional block without knowing one
    — every scalar and every list. A gate stays shut, since opening it takes
    its own "Yes" answer's UUID and not just any value.
    """

    def __contains__(self, path: str) -> bool:
        return True

    def __getitem__(self, path: str) -> str:
        return "answered"


def _render(body: str, replies) -> dict:
    """The template run by Jinja itself, and the document it produced.

    DSW's three reply filters are stubbed: ``reply_path`` joins a chain of
    UUIDs into one key, ``reply_str_value`` hands back the stored reply, and
    ``reply_items`` gives a list question one item to iterate.
    """
    env = jinja2.Environment()
    env.filters["reply_path"] = lambda parts: ".".join(str(p) for p in parts)
    env.filters["reply_str_value"] = lambda reply: reply
    env.filters["reply_items"] = lambda reply: ["item-0"]
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
    have, and the template has to hold for it — so it is written here rather
    than waited for.
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
    """The pair's whole invariant. They are published as two packages and
    nothing in DSW checks they agree: a UUID drifting on either side is a
    question whose answer silently never reaches the document."""
    km_entities = {
        event["entityUuid"]
        for event in build_km_bundle(project, created_at=STAMP)["packages"][0]["events"]
    }
    assert _uuids_in(body) - km_entities == set()


def test_the_template_is_allowed_to_render_exactly_its_own_km(project, bundle):
    km = build_km_bundle(project, created_at=STAMP)
    assert bundle["id"] == km["id"]
    assert bundle["templateId"] == km["kmId"]
    allowed = bundle["allowedPackages"][0]
    assert allowed["kmId"] == km["kmId"]
    assert allowed["orgId"] == project.config["organizationId"]


def test_the_answer_table_translates_what_the_km_stores(project, body):
    """DSW stores an answer's UUID, not its label; AL is how the document
    gets the word back. Every key must therefore be a KM answer."""
    km_entities = {
        event["entityUuid"]
        for event in build_km_bundle(project, created_at=STAMP)["packages"][0]["events"]
    }
    al = body.split("{%- set AL = ", 1)[1].split(" -%}", 1)[0]
    assert _uuids_in(al) <= km_entities


def test_the_other_sentinel_is_kept_out_of_the_answer_table(body):
    """The lookup falling back to 'other' is what detects the "Other" answer.
    Give it a label and the fallback never fires, and a manually entered value
    is lost."""
    al = body.split("{%- set AL = ", 1)[1].split(" -%}", 1)[0]
    assert other_answer_uuid(SUGGESTED) not in al


# What the template must be


def test_the_body_is_jinja_that_parses(body):
    """The generator writes Jinja and never runs it, so nothing else in the
    pipeline would notice a syntax error before DSW hits it at render time,
    in front of a researcher."""
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
    that: `cost { type?, unit? }` is an ordinary shape for a standard to
    declare, and forbidding it would be asking the rules to lie about the
    standard so that the generator has an easier time.

    It takes a filled object to fail. Answer nothing and every block stays
    shut, which is why both are asserted here."""
    body = _body_from_rules(tmp_path, ANCHORLESS)
    answered = f"{chapter_uuid('contact')}.{question_uuid(('contact', 'mbox'))}"

    assert _render(body, {answered: "marie@example.org"})["dmp"]["contact"] == {
        "mbox": "marie@example.org"
    }
    assert _render(body, {})["dmp"]["contact"] == {}


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
    """Including the file UUID: derived from the package id, so that two
    generations of one project differ in nothing a reader can see."""
    assert build_template_bundle(project, created_at=STAMP) == build_template_bundle(
        project, created_at=STAMP
    )


def test_bumping_the_project_version_gives_the_file_a_new_uuid(project, bundle):
    """DSW keys a file's content by this UUID: reuse it across published
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
