"""The decisions the generators are not allowed to disagree on.

``field_kind`` is the one that matters: every kind it can return is a different
DSW entity in the KM and a different render in the template, so a kind nobody
tests is a pair of packages that can be published half-wrong. Every branch is
covered here, from a field built for it, rather than from whichever fields the
glider rules happen to contain.
"""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from dsw.common import (
    FIELD_KINDS,
    computed_fields_from_config,
    field_kind,
    needs_a_synthetic_escape,
    package_id,
    readme_head,
    readme_tail,
    rules_provenance_line,
    standard_label,
    strip_markdown,
    top_level_split,
    utc_timestamp,
)
from dsw.generate_km import build_km_bundle
from dsw.generate_template import build_template_bundle
from project import Field, Model, Project, assemble_project

GLIDER_CONFIG = Path(__file__).parent.parent / "configs" / "projects" / "glider.yaml"


def _field(name="title", path=None, cardinality="0..1", type="string", **kw) -> Field:
    path = path or (name,)
    return Field(
        name=name,
        path=path,
        dotted_path=".".join(path),
        cardinality=cardinality,
        type=type,
        origin="rda_dcs",
        **kw,
    )


# What a field becomes


@pytest.mark.parametrize(
    "expected, field",
    [
        ("value", _field()),
        ("value_multi", _field(cardinality="0..n")),
        ("boolean", _field(type="boolean")),
        ("object_inline", _field(type="object", cardinality="1")),
        ("object_gated", _field(type="object", cardinality="0..1")),
        ("list", _field(type="object", cardinality="0..n")),
        ("options_strict", _field(allowed_values=("a", "b"))),
        ("options_strict_multi", _field(cardinality="1..n", allowed_values=("a",))),
        ("options_suggested", _field(suggested_values=("a", "b"))),
        (
            "options_suggested_multi",
            _field(cardinality="0..n", suggested_values=("a",)),
        ),
    ],
)
def test_every_kind_a_field_can_be(expected, field):
    assert field_kind(field, computed_fields=set()) == expected


_ONE_OF_EACH_KIND = {
    "computed": _field(name="dmp_id"),
    "value": _field(),
    "value_multi": _field(cardinality="0..n"),
    "boolean": _field(type="boolean"),
    "options_strict": _field(allowed_values=("a", "b")),
    "options_suggested": _field(suggested_values=("a", "b")),
    "options_strict_multi": _field(cardinality="0..n", allowed_values=("a",)),
    "options_suggested_multi": _field(cardinality="0..n", suggested_values=("a",)),
    "object_inline": _field(type="object", cardinality="1"),
    "object_gated": _field(type="object", cardinality="0..1"),
    "list": _field(type="object", cardinality="0..n"),
}


def test_the_kinds_are_declared_where_the_generators_read_them():
    """``FIELD_KINDS`` is what a generator dispatches over, so it has to be
    the whole of what ``field_kind`` can answer, a kind returned but not listed
    is one nothing had to handle."""
    assert set(FIELD_KINDS) == set(_ONE_OF_EACH_KIND)
    for kind, field in _ONE_OF_EACH_KIND.items():
        assert field_kind(field, {"dmp_id"}) == kind


@pytest.mark.parametrize("kind", FIELD_KINDS)
def test_both_generators_know_what_to_do_with_every_kind(kind):
    """The pair's third failure mode, after a drifted UUID and a chain read
    from the wrong parent: a kind added here and handled by one generator
    only. Dispatched on a default rather than named, it would come out as a
    plain value question on one side and something else on the other, two
    packages that cannot be filled and nothing red.

    A field of each kind, through both, on a model of one field: neither may
    raise, and each must put something in its artifact."""
    field = _ONE_OF_EACH_KIND[kind]
    if field.type == "object":
        field = replace(
            field, children=(_field(name="leaf", path=(*field.path, "leaf")),)
        )
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    model = Model(
        base_standard="synthetic",
        extension_standards=(),
        fields=(field,),
        standard_versions=(("synthetic", "1.0.0"),),
    )
    project = Project(config=config, model=model)

    km = build_km_bundle(project, created_at="2026-01-01T00:00:00.000Z")
    assert km["packages"][0]["events"], "the KM emitted nothing at all"
    template = build_template_bundle(project, created_at="2026-01-01T00:00:00.000Z")
    assert template["files"][0]["content"]


def test_a_strict_vocabulary_wins_over_a_suggested_one():
    """Both can be set once a tightening replaces suggestions with an
    allowed list, and the constraint that binds is the one that decides."""
    field = _field(allowed_values=("a",), suggested_values=("a", "b"))
    assert field_kind(field, set()) == "options_strict"


def test_only_a_suggested_vocabulary_naming_no_escape_of_its_own_gets_one():
    """RDA DCS and DataCite both end several vocabularies with a value
    meaning "none of those listed", spelled ``other`` by one and ``Other`` by the
    other, and neither gives a field beside it to say which.

    So a synthetic "Other" answer is added only where the vocabulary admits
    values it does not list and names no escape itself. Both generators read
    this one answer: a KM offering the synthetic answer where the template
    reads the declared value is a pair nobody can fill, and on a vocabulary
    spelling it in lower case the two are the same entity, a UUID being
    derived from the value."""
    assert needs_a_synthetic_escape(_field(suggested_values=("ror", "grid")))
    assert not needs_a_synthetic_escape(_field(suggested_values=("orcid", "other")))
    assert not needs_a_synthetic_escape(_field(suggested_values=("Doer", "Other")))
    # A closed vocabulary admits nothing else, whether or not it names one.
    assert not needs_a_synthetic_escape(_field(allowed_values=("url", "other")))
    assert not needs_a_synthetic_escape(_field(allowed_values=("a", "b")))
    assert not needs_a_synthetic_escape(_field())


def test_computed_applies_to_top_level_fields_only():
    """``dmp_id`` is computed, and a nested field that happens to share the
    name is a question like any other."""
    assert field_kind(_field(name="dmp_id"), {"dmp_id"}) == "computed"
    nested = _field(name="dmp_id", path=("project", "dmp_id"))
    assert field_kind(nested, {"dmp_id"}) == "value"


def test_computed_beats_every_other_kind():
    """It is tested first on purpose, a computed object field must not
    become a chapter of questions nobody answers."""
    field = _field(name="created", type="object", cardinality="0..n")
    assert field_kind(field, {"created"}) == "computed"


# Which fields the template fills instead of asking


def test_dmp_id_is_always_computed():
    assert computed_fields_from_config({}) == {"dmp_id"}


def test_timestamps_are_computed_only_under_auto_timestamps():
    assert computed_fields_from_config({"auto_timestamps": True}) == {
        "dmp_id",
        "created",
        "modified",
    }
    assert computed_fields_from_config({"auto_timestamps": False}) == {"dmp_id"}


# The chapter split


def test_objects_become_chapters_and_scalars_stay_general():
    general, chapters = top_level_split(assemble_project(GLIDER_CONFIG).model)
    assert {f.type for f in chapters} == {"object"}
    assert "object" not in {f.type for f in general}


def test_nothing_is_dropped_by_the_split():
    """The rules are the whole questionnaire, every field they declare is
    asked, so this is a split and not a filter."""
    model = assemble_project(GLIDER_CONFIG).model
    general, chapters = top_level_split(model)
    assert len(general) + len(chapters) == len(model.fields)


# How a standard is written, and how it is shown


def test_a_standard_is_shown_in_upper_case():
    """One spelling in code, snake_case, and the displayable form is derived
    here rather than declared beside it."""
    assert standard_label("rda_dcs") == "RDA_DCS"
    assert standard_label("ostrails") == "OSTRAILS"


# The rest


def test_the_package_id_is_the_three_fields_dsw_reads():
    """Three fields, joined in the order DSW reads them, said on a config of
    its own where all three values differ and a swap would show. The real
    project only has to agree on the two that are not meant to move, pinning
    its version here would make publishing a correction start with a red
    test."""
    assert package_id({"organizationId": "o", "id": "p", "version": "9"}) == "o:p:9"
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    assert package_id(config) == f"socib:glider:{config['version']}"


def test_the_provenance_line_names_every_standard_and_version():
    """A fact, with no bullet of its own, how a compatibility fact is set is
    ``readme_tail``'s to decide."""
    line = rules_provenance_line(assemble_project(GLIDER_CONFIG).model)
    assert line == "Rules: RDA_DCS 1.0.0, OSTRAILS 1.0.0"


@pytest.mark.parametrize(
    "markdown, plain",
    [
        ("a [link](http://x) here", "a link here"),
        ("**bold** and *italic*", "bold and italic"),
        ("nothing to strip", "nothing to strip"),
        ("**[both](http://x)**", "both"),
    ],
)
def test_markdown_reduces_to_its_plain_reading(markdown, plain):
    """DSW renders a package's readme as Markdown but its description as
    plain text, and both come from the same config prose."""
    assert strip_markdown(markdown) == plain


def test_a_readme_opens_with_the_project_and_ends_with_its_references():
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    head = readme_head(config, "Knowledge Model")
    tail = readme_tail(config, ["Compatible with everything", "And with this"])
    assert head[0] == "# SOCIB Glider : Knowledge Model"
    assert tail[-1] == "- [SOCIB](https://www.socib.es)"
    assert tail[2:4] == ["- Compatible with everything", "- And with this"]


def test_both_packages_set_their_compatibility_facts_the_same_way():
    """Both READMEs get their compatibility facts marked the same way, by
    ``readme_tail`` and not by either caller."""
    project = assemble_project(GLIDER_CONFIG)
    stamp = "2026-01-01T00:00:00.000Z"
    readmes = (
        build_km_bundle(project, created_at=stamp)["packages"][0]["readme"],
        build_template_bundle(project, created_at=stamp)["readme"],
    )
    for readme in readmes:
        facts = readme.split("## Compatibility\n\n", 1)[1].split("\n\n", 1)[0]
        assert facts.splitlines()
        assert all(line.startswith("- ") for line in facts.splitlines()), facts


def test_the_timestamp_is_the_shape_dsw_expects():
    stamp = utc_timestamp()
    assert len(stamp) == 24 and stamp.endswith(".000Z") and stamp[10] == "T"
