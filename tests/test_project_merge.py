"""project/merge.py: the real rules files merge into one Model, and the
tighten-only merge semantics accept (and record) every legitimate restriction
while rejecting every loosening, reshaping, or widening."""

import json
from pathlib import Path

import pytest

from project import (
    Model,
    RulesConflictError,
    RulesSetError,
    merge_rules,
)

RULES_DIR = Path(__file__).parent.parent / "rules" / "standards"
REAL_FILES = [
    RULES_DIR / "rda_dcs" / "1.0.0.json",
    RULES_DIR / "ostrails" / "1.0.0.json",
]


# The real files


def test_real_files_merge():
    model = merge_rules(REAL_FILES)
    assert model.base_standard == "rda_dcs"
    assert model.extension_standards == ("ostrails",)


def test_real_files_input_order_does_not_matter():
    shuffled = merge_rules([REAL_FILES[1], REAL_FILES[0]])
    assert shuffled.base_standard == "rda_dcs"


def test_real_files_origins():
    model = merge_rules(REAL_FILES)
    by_path = {f.dotted_path: f for f in model.walk()}
    # A base field, an extension's own new field, and a structural parent the
    # extension redeclares to reach its own leaves (base origin must win).
    assert by_path["dmp.title"].origin == "rda_dcs"
    assert by_path["dmp.dataset[].methodology"].origin == "ostrails"
    assert by_path["dmp.dataset[]"].origin == "rda_dcs"


def test_real_files_walk_covers_every_field():
    model = merge_rules(REAL_FILES)
    fields = list(model.walk())
    assert len(fields) > 100
    assert all(f.dotted_path.startswith("dmp.") for f in fields)


# Synthetic bases/extensions for the merge semantics


def _doc(tmp_path, name, extends, dmp, version="1.0.0"):
    # <standard>/<version>.json: load_rules_file checks that a file sits where
    # it says, so even a synthetic model needs the versioned layout — and a
    # standard is spelled the same in the directory and in the document.
    path = tmp_path / name / f"{version}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"standard": name, "version": version, "extends": extends, "dmp": dmp}
        )
    )
    return path


def _merge(tmp_path, base_dmp, ext_dmp) -> Model:
    return merge_rules(
        [_doc(tmp_path, "base", False, base_dmp), _doc(tmp_path, "ext", True, ext_dmp)]
    )


def _merge_conflicts(tmp_path, base_dmp, ext_dmp) -> str:
    with pytest.raises(RulesConflictError) as excinfo:
        _merge(tmp_path, base_dmp, ext_dmp)
    return str(excinfo.value)


STRING_1 = {"_cardinality": "1", "_type": "string"}
STRING_01 = {"_cardinality": "0..1", "_type": "string"}


def test_new_extension_field_stamped_with_its_origin(tmp_path):
    model = _merge(
        tmp_path,
        {"title": dict(STRING_1)},
        {"extra": {"_cardinality": "0..1", "_type": "object", "name": dict(STRING_1)}},
    )
    by_path = {f.dotted_path: f for f in model.walk()}
    assert by_path["dmp.title"].origin == "base"
    assert by_path["dmp.extra"].origin == "ext"
    assert by_path["dmp.extra.name"].origin == "ext"  # whole subtree stamped


def test_identical_redeclaration_merges_silently(tmp_path):
    model = _merge(tmp_path, {"title": dict(STRING_1)}, {"title": dict(STRING_1)})
    (title,) = model.walk()
    assert title.origin == "base"
    assert title.tightenings == ()


def test_cardinality_tightening_accepted_and_recorded(tmp_path):
    model = _merge(tmp_path, {"title": dict(STRING_01)}, {"title": dict(STRING_1)})
    (title,) = model.walk()
    assert title.cardinality == "1"
    assert title.is_required
    (tightening,) = title.tightenings
    assert (tightening.standard, tightening.aspect) == ("ext", "cardinality")
    assert (tightening.before, tightening.after) == ("0..1", "1")


def test_cardinality_loosening_rejected(tmp_path):
    conflicts = _merge_conflicts(
        tmp_path, {"title": dict(STRING_1)}, {"title": dict(STRING_01)}
    )
    assert "loosens" in conflicts


def test_cardinality_reshaping_rejected(tmp_path):
    conflicts = _merge_conflicts(
        tmp_path,
        {"keyword": {"_cardinality": "0..n", "_type": "string"}},
        {"keyword": dict(STRING_1)},
    )
    assert "shape" in conflicts


def test_type_disagreement_rejected(tmp_path):
    conflicts = _merge_conflicts(
        tmp_path,
        {"issued": {"_cardinality": "1", "_type": "date"}},
        {"issued": {"_cardinality": "1", "_type": "string"}},
    )
    assert "_type" in conflicts


def test_vocabulary_subset_accepted_and_recorded(tmp_path):
    model = _merge(
        tmp_path,
        {"mode": {**STRING_1, "_allowed_values": ["rt", "dt", "dm"]}},
        {"mode": {**STRING_1, "_allowed_values": ["rt"]}},
    )
    (mode,) = model.walk()
    assert mode.allowed_values == ("rt",)
    (tightening,) = mode.tightenings
    assert tightening.aspect == "allowed_values"
    assert tightening.before == ["rt", "dt", "dm"]


def test_vocabulary_widening_rejected(tmp_path):
    conflicts = _merge_conflicts(
        tmp_path,
        {"mode": {**STRING_1, "_allowed_values": ["rt", "dt"]}},
        {"mode": {**STRING_1, "_allowed_values": ["rt", "track"]}},
    )
    assert "widens" in conflicts
    assert "track" in conflicts


def test_extension_may_close_an_open_field(tmp_path):
    model = _merge(
        tmp_path,
        {"language": dict(STRING_01)},
        {"language": {**STRING_01, "_suggested_values": ["eng", "spa", "cat"]}},
    )
    (language,) = model.walk()
    assert language.suggested_values == ("eng", "spa", "cat")
    (tightening,) = language.tightenings
    assert tightening.before is None


def test_an_extension_fills_a_missing_description_and_may_repeat_one(tmp_path):
    """Describing a field the base left undescribed is the useful case, and
    repeating a description word for word is what redeclaring a structural
    parent looks like. Neither is a disagreement."""
    model = _merge(
        tmp_path,
        {
            "title": {**STRING_1, "_description": "Base says."},
            "language": dict(STRING_01),
        },
        {
            "title": {**STRING_1, "_description": "Base says."},
            "language": {**STRING_01, "_description": "Ext fills the gap."},
        },
    )
    by_path = {f.dotted_path: f for f in model.walk()}
    assert by_path["dmp.title"].description == "Base says."
    assert by_path["dmp.language"].description == "Ext fills the gap."


def test_two_files_describing_one_field_differently_is_a_conflict(tmp_path):
    """It used to be a silent drop — the base's wording kept, the extension's
    discarded without a word. Which is the fault `_chapter_description` has a
    coherence check for: prose the generators ignore in silence, where the
    author has every reason to believe it was taken.

    Whether an extension should be able to *replace* a description is a
    question this merge does not answer. Refusing is what says so."""
    with pytest.raises(RulesConflictError) as raised:
        _merge(
            tmp_path,
            {"title": {**STRING_1, "_description": "Base says."}},
            {"title": {**STRING_1, "_description": "Ext says."}},
        )
    (problem,) = raised.value.problems
    assert "dmp.title" in problem and "_description" in problem
    assert "base" in problem and "ext" in problem


def test_all_conflicts_reported_at_once(tmp_path):
    conflicts = _merge_conflicts(
        tmp_path,
        {"title": dict(STRING_1), "issued": {"_cardinality": "1", "_type": "date"}},
        {
            "title": dict(STRING_01),
            "issued": {"_cardinality": "1", "_type": "string"},
        },
    )
    assert "dmp.title" in conflicts
    assert "dmp.issued" in conflicts


# Ill-formed sets of files


def test_two_bases_rejected(tmp_path):
    with pytest.raises(RulesSetError, match="exactly one base"):
        merge_rules(
            [
                _doc(tmp_path, "a", False, {"title": dict(STRING_1)}),
                _doc(tmp_path, "b", False, {"title": dict(STRING_1)}),
            ]
        )


def test_no_base_rejected(tmp_path):
    with pytest.raises(RulesSetError, match="exactly one base"):
        merge_rules([_doc(tmp_path, "a", True, {"title": dict(STRING_1)})])


def test_duplicate_standard_names_rejected(tmp_path):
    first = _doc(tmp_path, "a", False, {"title": dict(STRING_1)})
    # Same standard at another version: two files, one name, distinct paths.
    duplicate = _doc(tmp_path, "a", True, {"title": dict(STRING_1)}, version="2.0.0")
    with pytest.raises(RulesSetError, match="unique"):
        merge_rules([first, duplicate])


def test_every_problem_with_the_set_is_reported_at_once(tmp_path):
    """A duplicate standard and a missing base are both visible from one pass,
    so one attempt must report both rather than costing two round trips."""
    files = [
        _doc(tmp_path, "a", True, {"title": dict(STRING_1)}),
        _doc(tmp_path, "a", True, {"title": dict(STRING_1)}, version="2.0.0"),
    ]
    with pytest.raises(RulesSetError) as excinfo:
        merge_rules(files)
    assert len(excinfo.value.problems) == 2
    assert "unique" in excinfo.value.problems[0]
    assert "exactly one base" in excinfo.value.problems[1]


# Versions. Placement itself is loader.py's, and lives in test_rules_loader.py.


def test_versioned_paths_merge_and_stamp_their_versions(tmp_path):
    root = tmp_path / "standards"
    for standard, version, extends in (
        ("rda_dcs", "1.0.0", False),
        ("ostrails", "2.1.0", True),
    ):
        path = root / standard / f"{version}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "standard": standard,
                    "version": version,
                    "extends": extends,
                    "dmp": {"title": dict(STRING_1)},
                }
            )
        )
    model = merge_rules(
        [root / "rda_dcs" / "1.0.0.json", root / "ostrails" / "2.1.0.json"]
    )
    assert model.standard_versions == (("rda_dcs", "1.0.0"), ("ostrails", "2.1.0"))


def test_model_stamps_the_declared_version_not_the_filename(tmp_path):
    # merge_rules is layout-agnostic: handed a file outside the versioned tree,
    # it must still report the version the document declares.
    path = _doc(tmp_path, "base", False, {"title": dict(STRING_1)}, version="3.2.1")
    assert merge_rules([path]).standard_versions == (("base", "3.2.1"),)


def test_real_files_merge_from_their_versioned_paths():
    model = merge_rules(REAL_FILES)
    assert model.standard_versions == (
        ("rda_dcs", "1.0.0"),
        ("ostrails", "1.0.0"),
    )


# Field conveniences consumers rely on


def test_dotted_path_marks_every_list_ancestor(tmp_path):
    model = _merge(
        tmp_path,
        {
            "dataset": {
                "_cardinality": "1..n",
                "_type": "object",
                "distribution": {
                    "_cardinality": "0..n",
                    "_type": "object",
                    "title": dict(STRING_1),
                },
            }
        },
        # Nothing to add: a rules file may declare neither no field at all nor
        # a childless object, so the extension redeclares a whole base branch
        # identically, down to a leaf — the merge's no-op, and it leaves the
        # walk untouched.
        {
            "dataset": {
                "_cardinality": "1..n",
                "_type": "object",
                "distribution": {
                    "_cardinality": "0..n",
                    "_type": "object",
                    "title": dict(STRING_1),
                },
            }
        },
    )
    paths = [f.dotted_path for f in model.walk()]
    assert paths == [
        "dmp.dataset[]",
        "dmp.dataset[].distribution[]",
        "dmp.dataset[].distribution[].title",
    ]


# Conveniences consumers read, and the audit record


def test_is_list_reads_the_cardinality():
    model = merge_rules(REAL_FILES)
    by_path = {f.dotted_path: f for f in model.walk()}
    assert by_path["dmp.dataset[]"].is_list
    assert not by_path["dmp.title"].is_list


def test_standards_is_the_base_then_its_extensions():
    assert merge_rules(REAL_FILES).standards == ("rda_dcs", "ostrails")


def test_an_identical_vocabulary_records_no_tightening(tmp_path):
    """Redeclaring a vocabulary unchanged is a no-op, not a restriction: it
    must not leave a Tightening whose before equals its after."""
    vocabulary = {**STRING_1, "_allowed_values": ["rt", "dt"]}
    model = _merge(tmp_path, {"mode": dict(vocabulary)}, {"mode": dict(vocabulary)})
    (mode,) = model.walk()
    assert mode.allowed_values == ("rt", "dt")
    assert mode.tightenings == ()


def test_a_vocabulary_tightening_is_recorded_under_its_aspect_name(tmp_path):
    # The aspect is a declared name, not the metadata key with its underscore
    # stripped: a consumer matching on it must survive a key being renamed.
    model = _merge(
        tmp_path,
        {"mode": {**STRING_1, "_suggested_values": ["rt", "dt"]}},
        {"mode": {**STRING_1, "_suggested_values": ["rt"]}},
    )
    (tightening,) = next(model.walk()).tightenings
    assert tightening.aspect == "suggested_values"
