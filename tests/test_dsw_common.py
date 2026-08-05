"""The decisions the generators are not allowed to disagree on.

`field_kind` is the one that matters: every kind it can return is a different
DSW entity in the KM and a different render in the template, so a kind nobody
tests is a pair of packages that can be published half-wrong. Every branch is
covered here, from a field built for it, rather than from whichever fields the
glider rules happen to contain.
"""

from pathlib import Path

import pytest
import yaml

from dsw.common import (
    computed_fields_from_config,
    field_kind,
    package_id,
    readme_head,
    readme_tail,
    rules_provenance_line,
    standard_label,
    strip_markdown,
    top_level_split,
    utc_timestamp,
)
from project import Field, assemble_project

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


def test_a_strict_vocabulary_wins_over_a_suggested_one():
    """Both can be set once a tightening replaces suggestions with an allowed
    list; the constraint that binds is the one that decides."""
    field = _field(allowed_values=("a",), suggested_values=("a", "b"))
    assert field_kind(field, set()) == "options_strict"


def test_computed_applies_to_top_level_fields_only():
    """`dmp_id` is computed; a nested field that happens to share the name is
    a question like any other."""
    assert field_kind(_field(name="dmp_id"), {"dmp_id"}) == "computed"
    nested = _field(name="dmp_id", path=("project", "dmp_id"))
    assert field_kind(nested, {"dmp_id"}) == "value"


def test_computed_beats_every_other_kind():
    """It is tested first on purpose: a computed object field must not become
    a chapter of questions nobody answers."""
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
    """The rules are the whole questionnaire: every field they declare is
    asked, so this is a split and not a filter."""
    model = assemble_project(GLIDER_CONFIG).model
    general, chapters = top_level_split(model)
    assert len(general) + len(chapters) == len(model.fields)


# How a standard is written, and how it is shown


def test_a_standard_is_shown_in_upper_case():
    """One spelling in code, snake_case; the displayable form is derived here
    and never declared beside it."""
    assert standard_label("rda_dcs") == "RDA_DCS"
    assert standard_label("ostrails") == "OSTRAILS"


# The rest


def test_the_package_id_is_the_three_fields_dsw_reads():
    """Three fields, joined in the order DSW reads them — said on a config of
    its own, where all three values differ and a swap would show. The real
    project only has to agree on the two that are not meant to move: pinning
    its version here would make publishing a correction start with a red
    test."""
    assert package_id({"organizationId": "o", "id": "p", "version": "9"}) == "o:p:9"
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    assert package_id(config) == f"socib:glider:{config['version']}"


def test_the_provenance_line_names_every_standard_and_version():
    line = rules_provenance_line(assemble_project(GLIDER_CONFIG).model)
    assert line == "- Rules: RDA_DCS 1.0.0, OSTRAILS 1.0.0"


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
    head = readme_head(config, "Knowledge model")
    tail = readme_tail(config, ["- Compatible with everything."])
    assert head[0] == "# SOCIB Glider : Knowledge model"
    assert tail[-1] == "- [SOCIB](https://www.socib.es)"
    assert "- Compatible with everything." in tail


def test_the_timestamp_is_the_shape_dsw_expects():
    stamp = utc_timestamp()
    assert len(stamp) == 24 and stamp.endswith(".000Z") and stamp[10] == "T"
