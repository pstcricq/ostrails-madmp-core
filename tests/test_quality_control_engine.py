"""quality_control/engine.py: what a check says about one concrete value.

The engine takes a merged Model and a document, so most tests here build a
tiny standard in ``tmp_path`` rather than leaning on the real rules: one field
with one constraint, and one document that satisfies it or does not, which is
what makes a failure name its own cause. The real files are used only where
what is being checked is that the two fit together.
"""

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from project import Model, assemble_project, merge_rules
from quality_control import (
    SCALAR_TYPES,
    CheckResult,
    has_failures,
    results_to_dicts,
    run_qc,
)

ROOT = Path(__file__).parent.parent
RULES_DIR = ROOT / "rules" / "standards"
PROJECT_CONFIGS = sorted((ROOT / "configs" / "projects").glob("*.yaml"))

STRING_1 = {"_cardinality": "1", "_type": "string"}
STRING_01 = {"_cardinality": "0..1", "_type": "string"}
STRING_1N = {"_cardinality": "1..n", "_type": "string"}
STRING_0N = {"_cardinality": "0..n", "_type": "string"}


def _model(tmp_path, dmp, name="base") -> Model:
    """A one-file standard, laid out where the loader expects to find it."""
    path = tmp_path / name / "1.0.0.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"standard": name, "version": "1.0.0", "extends": False, "dmp": dmp})
    )
    return merge_rules([path])


def _check(tmp_path, dmp_rules, dmp_document, category=None) -> list[CheckResult]:
    """Every result, or only those of one category."""
    results = run_qc(_model(tmp_path, dmp_rules), {"dmp": dmp_document})
    return [r for r in results if category is None or r.category == category]


def _statuses(results) -> dict[str, int]:
    return dict(Counter(r.status for r in results))


# A value each scalar type accepts, so a probe document is valid everywhere.
PROBE = {
    "string": "text",
    "number": 1,
    "boolean": True,
    "date": "2026-08-18",
    "datetime": "2026-08-18T09:00:00Z",
    "email": "albert@example.com",
    "url": "https://example.org/a",
    "currency": "EUR",
    "country_code": "ES",
    "language": "eng",
}


def _probe(model) -> dict:
    """A document answering every field the model declares, so that walking it
    reaches all of them. A vocabulary is answered with one of its own values,
    anything else with a value of its declared type."""

    def value(field):
        if field.type == "object":
            answer = {child.name: value(child) for child in field.children}
        elif field.allowed_values or field.suggested_values:
            answer = (field.allowed_values or field.suggested_values)[0]
        else:
            answer = PROBE[field.type]
        return [answer] if field.is_list else answer

    return {"dmp": {field.name: value(field) for field in model.fields}}


# The document's own shape


def test_a_document_with_no_dmp_object_says_only_that(tmp_path):
    """Nothing can be walked, so nothing is reported but the reason. Reporting
    every rule as missing instead would bury the one fact that matters."""
    results = run_qc(_model(tmp_path, {"title": dict(STRING_1)}), {"foo": 1})
    assert len(results) == 1
    assert (results[0].category, results[0].status) == ("structure", "fail")


@pytest.mark.parametrize("document", [{"dmp": []}, {"dmp": "x"}, [], "x", None])
def test_anything_that_is_not_a_dmp_object_fails_the_same_way(tmp_path, document):
    """A list, a string, or no mapping at all. The engine is handed whatever
    json.load returned, so none of these may raise."""
    results = run_qc(_model(tmp_path, {"title": dict(STRING_1)}), document)
    assert [(r.category, r.status) for r in results] == [("structure", "fail")]


def test_a_document_with_a_dmp_object_starts_with_a_pass(tmp_path):
    results = run_qc(_model(tmp_path, {"title": dict(STRING_1)}), {"dmp": {}})
    assert (results[0].category, results[0].status) == ("structure", "pass")


# Presence


def test_a_required_field_that_is_absent_fails(tmp_path):
    results = _check(tmp_path, {"title": dict(STRING_1)}, {}, "presence")
    assert [(r.status, "missing" in r.message) for r in results] == [("fail", True)]


def test_a_required_field_that_is_empty_fails_and_says_so(tmp_path):
    """The empty string is an absence, not a value. The document template
    emits every required scalar unconditionally, so an unanswered question
    arrives as "". Read as a value it would pass presence and type both."""
    results = _check(tmp_path, {"title": dict(STRING_1)}, {"title": ""}, "presence")
    assert [(r.status, "is empty" in r.message) for r in results] == [("fail", True)]


def test_spaces_are_a_value_and_not_an_absence(tmp_path):
    """Somebody typed that. Treating it as an absence would silently drop
    content the researcher can see in DSW."""
    results = _check(tmp_path, {"title": dict(STRING_1)}, {"title": "  "}, "presence")
    assert [r.status for r in results] == ["pass"]


def test_an_optional_field_that_is_absent_is_missing_and_never_fails(tmp_path):
    results = _check(tmp_path, {"note": dict(STRING_01)}, {}, "presence")
    assert [r.status for r in results] == ["missing"]
    assert not has_failures(results)


def test_an_empty_list_is_an_absence(tmp_path):
    """``[]`` is what a list question nobody answered renders as, so it has to
    read like a missing field and not like a list of zero."""
    required = _check(tmp_path, {"tag": dict(STRING_1N)}, {"tag": []}, "presence")
    optional = _check(tmp_path, {"tag": dict(STRING_0N)}, {"tag": []}, "presence")
    assert [r.status for r in required] == ["fail"]
    assert [r.status for r in optional] == ["missing"]


def test_an_absent_container_reports_once_and_says_nothing_underneath(tmp_path):
    """One result for the container, none for what it would have held. An
    optional object nobody filled in must not produce one line per field it
    declares."""
    rules = {
        "contact": {
            "_cardinality": "0..1",
            "_type": "object",
            "name": dict(STRING_1),
            "mbox": dict(STRING_1),
        }
    }
    results = _check(tmp_path, rules, {})
    assert [(r.category, r.status, r.instance_path) for r in results][1:] == [
        ("presence", "missing", "dmp.contact")
    ]


# Shape


def test_a_list_field_given_a_scalar_fails(tmp_path):
    results = _check(tmp_path, {"tag": dict(STRING_1N)}, {"tag": "one"}, "shape")
    assert [r.status for r in results] == ["fail"]
    assert "should be a list" in results[0].message


def test_a_single_field_given_a_list_fails(tmp_path):
    results = _check(tmp_path, {"title": dict(STRING_1)}, {"title": ["a"]}, "shape")
    assert [r.status for r in results] == ["fail"]
    assert "should be a single value" in results[0].message


def test_an_object_field_given_a_scalar_fails(tmp_path):
    rules = {"contact": {"_cardinality": "1", "_type": "object", "name": STRING_1}}
    results = _check(tmp_path, rules, {"contact": "Albert"}, "shape")
    assert [r.status for r in results] == ["fail"]
    assert "should be an object" in results[0].message


def test_a_scalar_field_given_an_object_fails(tmp_path):
    results = _check(tmp_path, {"title": dict(STRING_1)}, {"title": {"a": 1}}, "shape")
    assert [r.status for r in results] == ["fail"]
    assert "should be a scalar" in results[0].message


def test_a_list_reports_every_item_at_its_own_index(tmp_path):
    """One rule, several concrete spots. ``rule_path`` groups a report and
    ``instance_path`` is what somebody opens the file to fix."""
    rules = {"tag": {"_cardinality": "1..n", "_type": "number"}}
    results = _check(tmp_path, rules, {"tag": [1, "two", 3]}, "type")
    assert [(r.instance_path, r.status) for r in results] == [
        ("dmp.tag[0]", "pass"),
        ("dmp.tag[1]", "fail"),
        ("dmp.tag[2]", "pass"),
    ]
    assert {r.rule_path for r in results} == {"dmp.tag[]"}


# Types


VALID = {
    "string": "text",
    "number": 42,
    "boolean": True,
    "date": "2026-08-18",
    "datetime": "2026-08-18T09:00:00Z",
    "email": "albert@example.com",
    "url": "https://example.com/a",
    "currency": "EUR",
    "country_code": "ES",
    "language": "eng",
}
INVALID = {
    "string": 1,
    "number": True,  # a bool is an int in Python and must not pass as a number
    "boolean": "yes",
    "date": "2026-02-31",  # the calendar has no such day
    "datetime": "not a time",
    "email": "albert.example.com",
    "url": "example.com",
    "currency": "eur",
    "country_code": "ESP",
    "language": "en",
}


@pytest.mark.parametrize("scalar_type", sorted(VALID))
def test_every_scalar_type_accepts_its_own_value(tmp_path, scalar_type):
    rules = {"field": {"_cardinality": "1", "_type": scalar_type}}
    results = _check(tmp_path, rules, {"field": VALID[scalar_type]}, "type")
    assert [r.status for r in results] == ["pass"]


@pytest.mark.parametrize("scalar_type", sorted(INVALID))
def test_every_scalar_type_refuses_what_it_is_not(tmp_path, scalar_type):
    rules = {"field": {"_cardinality": "1", "_type": scalar_type}}
    results = _check(tmp_path, rules, {"field": INVALID[scalar_type]}, "type")
    assert [r.status for r in results] == ["fail"]


def test_a_date_must_be_written_the_one_way(tmp_path):
    """``date.fromisoformat`` alone accepts forms the rules do not mean, so the
    pattern is checked first."""
    rules = {"field": {"_cardinality": "1", "_type": "date"}}
    assert [
        r.status for r in _check(tmp_path, rules, {"field": "20260818"}, "type")
    ] == ["fail"]


# Vocabularies


def test_a_value_outside_a_closed_vocabulary_fails(tmp_path):
    rules = {
        "kind": {"_cardinality": "1", "_type": "string", "_allowed_values": ["a", "b"]}
    }
    inside = _check(tmp_path, rules, {"kind": "a"}, "allowed_values")
    outside = _check(tmp_path, rules, {"kind": "c"}, "allowed_values")
    assert [r.status for r in inside] == ["pass"]
    assert [r.status for r in outside] == ["fail"]


def test_a_value_outside_a_suggested_vocabulary_only_warns(tmp_path):
    """A suggestion is not a rule. Failing here would make every free-text
    answer a violation, and nothing in the standard says it is one."""
    rules = {
        "kind": {
            "_cardinality": "1",
            "_type": "string",
            "_suggested_values": ["a", "b"],
        }
    }
    results = _check(tmp_path, rules, {"kind": "other"}, "suggested_values")
    assert [r.status for r in results] == ["warning"]
    assert not has_failures(results)


# Unexpected keys


def test_a_key_no_rule_declares_fails(tmp_path):
    """The document must respect the rules it declares it was built from, so
    a key none of them knows is a violation and not a remark."""
    results = _check(tmp_path, {"title": dict(STRING_1)}, {"title": "t", "who": "x"})
    unexpected = [r for r in results if r.category == "unexpected"]
    assert [(r.status, r.instance_path) for r in unexpected] == [("fail", "dmp.who")]


def test_an_unexpected_key_is_caught_inside_an_object_too(tmp_path):
    """The check reads the document rather than the model, so it has to run
    at every level the walk reaches and not at the root alone."""
    rules = {"contact": {"_cardinality": "1", "_type": "object", "name": STRING_1}}
    results = _check(tmp_path, rules, {"contact": {"name": "Albert", "fax": "x"}})
    unexpected = [r for r in results if r.category == "unexpected"]
    assert [r.instance_path for r in unexpected] == ["dmp.contact.fax"]


# Where a constraint came from


def test_a_tightened_field_names_the_standard_that_tightened_it(tmp_path):
    """A researcher told a field is required deserves to know by whom, the
    base standard and an extension being fixed by different people."""
    base = tmp_path / "base" / "1.0.0.json"
    base.parent.mkdir(parents=True)
    base.write_text(
        json.dumps(
            {
                "standard": "base",
                "version": "1.0.0",
                "extends": False,
                "dmp": {"title": dict(STRING_01)},
            }
        )
    )
    ext = tmp_path / "ext" / "1.0.0.json"
    ext.parent.mkdir(parents=True)
    ext.write_text(
        json.dumps(
            {
                "standard": "ext",
                "version": "1.0.0",
                "extends": True,
                "dmp": {"title": dict(STRING_1)},
            }
        )
    )
    results = run_qc(merge_rules([base, ext]), {"dmp": {}})
    presence = next(r for r in results if r.category == "presence")
    assert presence.status == "fail"
    assert "required by ext" in presence.message
    assert "0..1 in base" in presence.message


# The single PASS/FAIL rule, and the shape the results travel in


def test_only_a_failure_fails_the_document(tmp_path):
    """Warnings and absences are reported and do not decide. A DMP that is
    merely incomplete on its optional half has to pass."""
    rules = {
        "note": dict(STRING_01),
        "kind": {"_cardinality": "1", "_type": "string", "_suggested_values": ["a"]},
    }
    results = _check(tmp_path, rules, {"kind": "free text"})
    assert _statuses(results)["warning"] == 1
    assert _statuses(results)["missing"] == 1
    assert not has_failures(results)


def test_the_results_are_json(tmp_path):
    """They are written to a file the next step reads, so nothing in them may
    be a value json cannot carry."""
    results = _check(tmp_path, {"title": dict(STRING_1)}, {"title": "t"})
    dicts = results_to_dicts(results)
    assert json.loads(json.dumps(dicts)) == dicts
    assert set(dicts[0]) == {
        "category",
        "status",
        "rule_path",
        "instance_path",
        "standard",
        "message",
    }


# Against the real rules


@pytest.mark.parametrize("config", PROJECT_CONFIGS, ids=lambda p: p.stem)
def test_every_project_pins_rules_the_engine_can_check(config):
    """The set a project actually pins, which no other test here sees: a rules
    file may declare a ``_type`` nothing in this repository implements, and a
    field the engine cannot check is only found the day a submitted DMP
    carries a value for it."""
    model = assemble_project(config).model
    declared = {field.type for field in model.walk() if field.type != "object"}
    assert declared <= set(SCALAR_TYPES)


@pytest.mark.parametrize("config", PROJECT_CONFIGS, ids=lambda p: p.stem)
def test_every_project_is_walked_whole(config):
    """The tie to the real data, one project at a time. Every field the merged
    rules declare is reported, and reported once, so a model this engine
    cannot walk fails here rather than on somebody's submission."""
    model = assemble_project(config).model
    results = run_qc(model, _probe(model))
    reported = {r.rule_path for r in results if r.category == "presence"}
    assert reported == {field.dotted_path for field in model.walk()}
    assert not [r for r in results if r.category == "unexpected"]


def test_an_empty_document_reports_the_top_level_and_stops_there():
    """The other end of the same walk: nothing is answered, so each top-level
    field says so once and nothing below it is reported at all."""
    model = assemble_project(PROJECT_CONFIGS[0]).model
    results = run_qc(model, {"dmp": {}})
    assert len(results) == len(model.fields) + 1
    assert has_failures(results)


def test_a_field_reports_the_standard_that_introduced_it():
    """Which standard to go and read is part of the report, and an extension
    is not the base."""
    model = assemble_project(PROJECT_CONFIGS[0]).model
    document = {"dmp": {"dataset": [{"methodology": "towed"}]}}
    by_path = {
        r.rule_path: r for r in run_qc(model, document) if r.category == "presence"
    }
    assert by_path["dmp.title"].standard == "rda_dcs"
    assert by_path["dmp.dataset[].methodology"].standard == "ostrails"


# What the engine can be handed


def test_the_engine_knows_every_type_the_meta_schema_allows():
    """The rules meta-schema enumerates the types a field may declare and the
    engine enumerates the ones it can check. A type added to one and not the
    other passes every per-file check there is, and only shows the day a
    document carries a value for that field."""
    schema = json.loads((ROOT / "rules" / "rules.schema.json").read_text())
    declared = set(schema["$defs"]["field"]["properties"]["_type"]["enum"])
    assert declared - {"object"} == set(SCALAR_TYPES)


@pytest.mark.parametrize("scalar_type", SCALAR_TYPES)
def test_every_named_scalar_type_is_actually_handled(tmp_path, scalar_type):
    """``SCALAR_TYPES`` is a tuple kept by hand next to the dispatch, so it has
    to be the list that dispatch really implements. An unknown type raises,
    so reaching a verdict at all is the assertion."""
    rules = {"field": {"_cardinality": "1", "_type": scalar_type}}
    results = _check(tmp_path, rules, {"field": "probe"}, "type")
    assert [r.status for r in results] in (["pass"], ["fail"])


def test_a_type_the_engine_does_not_know_raises(tmp_path):
    """Loudly, and never as a silent pass. A document checked against a type
    nobody implemented has not been checked."""
    field = _model(tmp_path, {"field": dict(STRING_1)}).fields[0]
    stand_in = Model(
        base_standard="base",
        extension_standards=(),
        fields=(replace(field, type="colour"),),
        standard_versions=(("base", "1.0.0"),),
    )
    with pytest.raises(ValueError, match="Unknown scalar type: colour"):
        run_qc(stand_in, {"dmp": {"field": "x"}})
