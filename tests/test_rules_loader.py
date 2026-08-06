"""rules/loader.py: the real rules files load clean, each layer of
validation (JSON Schema, then coherence) rejects what it's meant to, every
problem of a load is reported in one error, and a file's placement in the
versioned tree is checked against what the file declares."""

import json
from pathlib import Path

import pytest

from rules.loader import RulesFileError, load_rules_file

RULES_DIR = Path(__file__).parent.parent / "rules" / "standards"
REAL_FILES = ["rda_dcs/1.0.0.json", "ostrails/1.0.0.json"]


@pytest.mark.parametrize("filename", REAL_FILES)
def test_real_rules_file_loads(filename):
    doc = load_rules_file(RULES_DIR / filename)
    assert isinstance(doc["standard"], str)
    assert isinstance(doc["extends"], bool)
    assert doc["dmp"]


def _write(tmp_path, doc):
    """Writes at <slug>/<version>.json — load_rules_file checks placement, so
    a fixture that wants to exercise anything else must sit where it says."""
    # .get: a doc missing these keys is exactly what some tests are checking,
    # and it still has to reach the loader to be rejected there.
    directory = str(doc.get("standard", "unnamed"))
    path = tmp_path / directory / f"{doc.get('version', '1.0.0')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    return path


def _minimal_doc(**dmp_fields):
    return {
        "standard": "test",
        "version": "1.0.0",
        "extends": False,
        "dmp": dmp_fields,
    }


def _load_problems(tmp_path, doc) -> str:
    with pytest.raises(RulesFileError) as excinfo:
        load_rules_file(_write(tmp_path, doc))
    return str(excinfo.value)


def test_syntactically_broken_json_is_a_rules_file_error(tmp_path):
    """A trailing comma must not escape as a raw JSONDecodeError: callers
    (and scripts/validate_rules.py) catch RulesFileError and nothing else."""
    path = tmp_path / "test" / "1.0.0.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"standard": "test", "extends": false, "dmp": {},}')
    with pytest.raises(RulesFileError, match="invalid JSON"):
        load_rules_file(path)


def test_unreadable_path_is_a_rules_file_error(tmp_path):
    """Same promise for a path that is not there: whoever resolved it says
    which standard is missing and what exists instead, but a caller holding
    this entry point still catches one type and not two."""
    with pytest.raises(RulesFileError, match="cannot be read"):
        load_rules_file(tmp_path / "absent" / "1.0.0.json")


def test_minimal_valid_doc_loads(tmp_path):
    doc = _minimal_doc(title={"_cardinality": "1", "_type": "string"})
    assert load_rules_file(_write(tmp_path, doc))["standard"] == "test"


def test_non_snake_case_standard_rejected(tmp_path):
    """`standard` is the directory name and the spelling a config's pin
    writes, so it is a code identifier: one spelling, checked at the door.
    Anything a reader sees is derived from it."""
    doc = _minimal_doc(title={"_cardinality": "1", "_type": "string"})
    doc["standard"] = "RDA DCS"
    assert "standard" in _load_problems(tmp_path, doc)


def test_non_snake_case_field_name_rejected(tmp_path):
    """Field names reach the generators as question keys and reach QC as rule
    paths, so their shape is fixed here rather than apologised for there."""
    doc = _minimal_doc(Title={"_cardinality": "1", "_type": "string"})
    assert "'Title'" in _load_problems(tmp_path, doc)


def test_missing_top_level_keys_rejected(tmp_path):
    problems = _load_problems(tmp_path, {"dmp": {}})
    assert "standard" in problems
    assert "version" in problems
    assert "extends" in problems


def test_list_type_rejected(tmp_path):
    doc = _minimal_doc(dataset={"_cardinality": "1..n", "_type": "list"})
    assert "_type" in _load_problems(tmp_path, doc)


def test_empty_dmp_rejected(tmp_path):
    # A rules file that declares no field constrains nothing.
    assert "dmp: {} should be non-empty" in _load_problems(tmp_path, _minimal_doc())


def test_duplicate_vocabulary_value_rejected(tmp_path):
    doc = _minimal_doc(
        mode={"_cardinality": "1", "_type": "string", "_allowed_values": ["rt", "rt"]}
    )
    assert "_allowed_values" in _load_problems(tmp_path, doc)


def test_empty_vocabulary_value_rejected(tmp_path):
    doc = _minimal_doc(
        mode={"_cardinality": "1", "_type": "string", "_suggested_values": [""]}
    )
    assert "_suggested_values" in _load_problems(tmp_path, doc)


def test_unknown_cardinality_rejected(tmp_path):
    doc = _minimal_doc(title={"_cardinality": "2..n", "_type": "string"})
    assert "_cardinality" in _load_problems(tmp_path, doc)


def test_metadata_typo_rejected(tmp_path):
    doc = _minimal_doc(
        title={"_cardinality": "1", "_type": "string", "_descriptoin": "oops"}
    )
    assert "_descriptoin" in _load_problems(tmp_path, doc)


def test_missing_required_metadata_rejected(tmp_path):
    doc = _minimal_doc(title={"_type": "string"})
    assert "_cardinality" in _load_problems(tmp_path, doc)


def test_children_on_scalar_rejected(tmp_path):
    doc = _minimal_doc(
        title={
            "_cardinality": "1",
            "_type": "string",
            "identifier": {"_cardinality": "1", "_type": "string"},
        }
    )
    problems = _load_problems(tmp_path, doc)
    assert "dmp.title" in problems
    assert "only 'object' fields may have children" in problems


def test_childless_object_rejected(tmp_path):
    """An object is its children: without one it collects nothing, and the
    generators say so in four different ways depending on the cardinality —
    none of them an error. A base standard has no reason to declare one as a
    hook for an extension to fill, since it always has a field of its own to
    put there."""
    doc = _minimal_doc(cost={"_cardinality": "0..n", "_type": "object"})
    problems = _load_problems(tmp_path, doc)
    assert "dmp.cost" in problems
    assert "declares no child fields" in problems


def test_childless_object_rejected_deep_in_the_tree(tmp_path):
    doc = _minimal_doc(
        dataset={
            "_cardinality": "1..n",
            "_type": "object",
            "distribution": {"_cardinality": "0..1", "_type": "object"},
        }
    )
    assert "dmp.dataset.distribution" in _load_problems(tmp_path, doc)


def test_vocabulary_on_object_rejected(tmp_path):
    doc = _minimal_doc(
        dataset={
            "_cardinality": "1..n",
            "_type": "object",
            "_allowed_values": ["a"],
            "title": {"_cardinality": "1", "_type": "string"},
        }
    )
    assert "_allowed_values on an 'object' field" in _load_problems(tmp_path, doc)


def test_both_vocabularies_on_one_field_rejected(tmp_path):
    """A closed vocabulary and a recommended one contradict each other, and
    `field_kind` reads `_allowed_values` first: the suggested values would
    never reach a generator. Same fault as a misplaced `_chapter_description`
    — a declaration nothing carries."""
    doc = _minimal_doc(
        language={
            "_cardinality": "1",
            "_type": "string",
            "_allowed_values": ["eng"],
            "_suggested_values": ["spa"],
        }
    )
    problems = _load_problems(tmp_path, doc)
    assert "dmp.language" in problems
    assert "either closed or recommended" in problems


def test_one_vocabulary_at_a_time_accepted(tmp_path):
    """The rule is about the pair, not about either key: each on its own is
    the normal case."""
    for vocab_key in ("_allowed_values", "_suggested_values"):
        doc = _minimal_doc(
            language={"_cardinality": "1", "_type": "string", vocab_key: ["eng"]}
        )
        assert load_rules_file(_write(tmp_path, doc))["standard"] == "test"


def test_chapter_description_on_top_level_object_accepted(tmp_path):
    doc = _minimal_doc(
        dataset={
            "_cardinality": "1..n",
            "_type": "object",
            "_chapter_description": "The datasets of this DMP.",
            "title": {"_cardinality": "1", "_type": "string"},
        }
    )
    assert load_rules_file(_write(tmp_path, doc))["standard"] == "test"


def test_chapter_description_on_top_level_scalar_rejected(tmp_path):
    doc = _minimal_doc(
        title={
            "_cardinality": "1",
            "_type": "string",
            "_chapter_description": "Not a chapter.",
        }
    )
    problems = _load_problems(tmp_path, doc)
    assert "dmp.title" in problems
    assert "is not an object" in problems


def test_chapter_description_below_top_level_rejected(tmp_path):
    doc = _minimal_doc(
        dataset={
            "_cardinality": "1..n",
            "_type": "object",
            "distribution": {
                "_cardinality": "0..n",
                "_type": "object",
                "_chapter_description": "A nested object is never a chapter.",
                "title": {"_cardinality": "1", "_type": "string"},
            },
        }
    )
    problems = _load_problems(tmp_path, doc)
    assert "dmp.dataset.distribution" in problems
    assert "not a top-level field" in problems


def test_all_problems_reported_at_once(tmp_path):
    doc = _minimal_doc(
        title={"_cardinality": "2..n", "_type": "string"},
        dataset={"_cardinality": "1..n", "_type": "list"},
    )
    problems = _load_problems(tmp_path, doc)
    assert "dataset" in problems
    assert "title" in problems


def test_coherence_waits_for_a_schema_valid_document(tmp_path):
    """The layers are ordered, and the order is a precondition rather than a
    courtesy: layers 2 and 3 read `standard`, `version` and `dmp` unguarded,
    which is only safe once the schema has vouched for them. So a document
    wrong on both counts reports the schema alone — the coherence problem
    below (a child field under a string) stays unsaid until the first is
    fixed."""
    doc = _minimal_doc(
        title={
            "_cardinality": "2..n",
            "_type": "string",
            "child": {"_cardinality": "1", "_type": "string"},
        }
    )
    problems = _load_problems(tmp_path, doc)
    assert "_cardinality" in problems
    assert "only 'object' fields may have children" not in problems


def test_coherence_checked_deep_in_the_tree(tmp_path):
    doc = _minimal_doc(
        dataset={
            "_cardinality": "1..n",
            "_type": "object",
            "distribution": {
                "_cardinality": "0..n",
                "_type": "object",
                "format": {
                    "_cardinality": "0..n",
                    "_type": "string",
                    "oops": {"_cardinality": "1", "_type": "string"},
                },
            },
        }
    )
    assert "dmp.dataset.distribution.format" in _load_problems(tmp_path, doc)


# Placement: a file must declare the standard and the version its path names


def _placed(tmp_path, directory, filename, standard, version):
    """One rules file at <directory>/<filename>.json, declaring whatever
    `standard` and `version` say — so it can be made to contradict its path."""
    path = tmp_path / directory / f"{filename}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "standard": standard,
                "version": version,
                "extends": True,
                "dmp": {"title": {"_cardinality": "1", "_type": "string"}},
            }
        )
    )
    return path


def test_a_correctly_placed_file_loads(tmp_path):
    path = _placed(tmp_path, "rda_dcs", "1.0.0", "rda_dcs", "1.0.0")
    assert load_rules_file(path)["standard"] == "rda_dcs"


def test_a_file_declaring_another_standard_rejected(tmp_path):
    # Sits in ostrails/ but calls itself socib: provenance would name a
    # standard the directory never promised.
    path = _placed(tmp_path, "ostrails", "9.9.9", "socib", "9.9.9")
    with pytest.raises(RulesFileError) as excinfo:
        load_rules_file(path)
    assert "'socib'" in str(excinfo.value)
    assert "'ostrails'" in str(excinfo.value)


def test_a_file_declaring_another_version_rejected(tmp_path):
    # `cp 1.0.0.json 1.1.0.json`: same content, new name, silently a new
    # version until the declaration disagrees with the filename.
    path = _placed(tmp_path, "rda_dcs", "1.1.0", "rda_dcs", "1.0.0")
    with pytest.raises(RulesFileError) as excinfo:
        load_rules_file(path)
    assert "'1.0.0'" in str(excinfo.value)
    assert "'1.1.0'" in str(excinfo.value)


def test_a_file_wrong_on_both_counts_reports_both(tmp_path):
    path = _placed(tmp_path, "ostrails", "9.9.9", "socib", "1.0.0")
    with pytest.raises(RulesFileError) as excinfo:
        load_rules_file(path)
    assert excinfo.value.problems == [
        (
            "declares standard 'socib' but sits in directory 'ostrails', "
            "the two must agree."
        ),
        "declares version '1.0.0' but is named '9.9.9', the two must agree.",
    ]


def test_placement_is_checked_on_load_so_nobody_has_to_remember(tmp_path):
    """The price of that: a rules file only loads from <standard>/<version>.json.
    A scratch copy elsewhere is refused even though its contents are valid."""
    path = _placed(tmp_path, "somewhere", "scratch", "rda_dcs", "1.0.0")
    with pytest.raises(RulesFileError, match="must agree"):
        load_rules_file(path)


def test_a_misplaced_and_incoherent_file_reports_both_layers(tmp_path):
    """Coherence and layout are one verdict, not two passes: they are the two
    checks a schema-valid document still has to face, and a file that fails
    both says so once."""
    path = tmp_path / "ostrails" / "1.0.0.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "standard": "socib",
                "version": "1.0.0",
                "extends": True,
                "dmp": {
                    "title": {
                        "_cardinality": "1",
                        "_type": "string",
                        "child": {"_cardinality": "1", "_type": "string"},
                    }
                },
            }
        )
    )
    with pytest.raises(RulesFileError) as excinfo:
        load_rules_file(path)
    problems = str(excinfo.value)
    assert "only 'object' fields may have children" in problems
    assert "sits in directory 'ostrails'" in problems
