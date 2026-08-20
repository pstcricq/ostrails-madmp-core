"""quality_control/run.py: the command, from files on disk to an envelope.

The engine is covered on its own, so what is checked here is the wiring: the
two file formats the pins can arrive in, what the envelope promises to every
reader, the exit code CI gates on, and the errors a file from another
repository can arrive with.
"""

import json
from pathlib import Path

import pytest
import yaml

from quality_control import STATUSES
from quality_control.run import PinsFileError, main, read_pins

ROOT = Path(__file__).parent.parent
RULES_DIR = ROOT / "rules" / "standards"
PINS = [{"rda_dcs": "1.0.0"}, {"ostrails": "1.0.0"}]

# A DMP answering everything the merged rules require, so a run over it is the
# only one that can exercise the passing half.
COMPLETE = {
    "dmp": {
        "title": "Glider",
        "language": "eng",
        "created": "2026-08-18T09:00:00Z",
        "modified": "2026-08-18T09:00:00Z",
        "ethical_issues_exist": "no",
        "dmp_id": {"identifier": "https://example.org/a", "type": "url"},
        "contact": {
            "name": "Albert Einstein",
            "mbox": "albert@example.com",
            "contact_id": [{"identifier": "0000-0001-2345-6789", "type": "orcid"}],
        },
        "dataset": [
            {
                "title": "CTD",
                "personal_data": "no",
                "sensitive_data": "no",
                "dataset_id": {
                    "identifier": "https://doi.org/10.5281/x",
                    "type": "doi",
                },
            }
        ],
    }
}


def _write(path: Path, document) -> Path:
    path.write_text(json.dumps(document))
    return path


def _run(tmp_path, document, pins_file) -> tuple[int, dict]:
    """One full run, and the envelope it wrote."""
    output = tmp_path / "out" / "qc.json"
    code = main(
        [
            "--pins",
            str(pins_file),
            "--dmp",
            str(_write(tmp_path / "dmp.json", document)),
            "--json",
            str(output),
            "--rules-dir",
            str(RULES_DIR),
        ]
    )
    return code, json.loads(output.read_text())


@pytest.fixture
def sidecar(tmp_path) -> Path:
    """The provenance file a submission commits beside its DMP."""
    return _write(tmp_path / "dmp.meta.json", {"project": "glider", "rules": PINS})


# Where the pins come from


def test_the_pins_are_read_from_the_file_committed_beside_the_dmp(tmp_path, sidecar):
    """The whole point: a DMP is checked against the versions it was built
    with, which travel with it, and not against whatever a config pins now."""
    _, envelope = _run(tmp_path, COMPLETE, sidecar)
    assert envelope["rules_versions"] == {"rda_dcs": "1.0.0", "ostrails": "1.0.0"}
    assert envelope["standards"] == ["rda_dcs", "ostrails"]


def test_a_project_config_carries_the_same_key(tmp_path):
    """YAML by its suffix, and the one key both files agree on. Running the
    check by hand from madmp-core has no sidecar to point at."""
    config = tmp_path / "glider.yaml"
    config.write_text(yaml.safe_dump({"id": "glider", "rules": PINS}))
    _, envelope = _run(tmp_path, COMPLETE, config)
    assert envelope["rules_versions"] == {"rda_dcs": "1.0.0", "ostrails": "1.0.0"}


def test_the_real_config_and_the_real_sidecar_shape_agree(tmp_path):
    """The tie to the real data: the one project that exists is readable
    through this door, so the two writers have not drifted."""
    assert read_pins(ROOT / "configs" / "projects" / "glider.yaml") == PINS


# What the envelope promises


def test_a_passing_document_says_so_and_exits_zero(tmp_path, sidecar):
    """The gate a CI job hangs on. A green check must mean the document has
    no real violation, and nothing else."""
    code, envelope = _run(tmp_path, COMPLETE, sidecar)
    assert code == 0
    assert envelope["verdict"] == "pass"
    assert envelope["summary"]["fail"] == 0


def test_a_failing_document_says_so_and_exits_one(tmp_path, sidecar):
    code, envelope = _run(tmp_path, {"dmp": {}}, sidecar)
    assert code == 1
    assert envelope["verdict"] == "fail"
    assert envelope["summary"]["fail"] > 0


def test_a_warning_alone_still_passes(tmp_path, sidecar):
    """Suggestions do not gate. A researcher answering outside a recommended
    vocabulary must not be stopped by a check nobody can overrule."""
    document = json.loads(json.dumps(COMPLETE))
    document["dmp"]["contact"]["contact_id"][0]["type"] = "something else"
    code, envelope = _run(tmp_path, document, sidecar)
    assert envelope["summary"]["warning"] > 0
    assert (code, envelope["verdict"]) == (0, "pass")


def test_the_counts_add_up_to_the_lists(tmp_path, sidecar):
    """The summary exists so no reader recounts. It has to be the same
    answer, or two steps of one pipeline disagree about one run."""
    _, envelope = _run(tmp_path, COMPLETE, sidecar)
    summary = envelope["summary"]
    assert sum(summary[s] for s in STATUSES) == summary["total"]
    assert sum(len(envelope[s]) for s in STATUSES) == summary["total"]


def test_each_list_holds_exactly_what_the_summary_counted(tmp_path, sidecar):
    """The invariant a reader shows results by severity on: the list under a
    status and the count under the same name are one answer, not two."""
    _, envelope = _run(tmp_path, COMPLETE, sidecar)
    for status in STATUSES:
        assert len(envelope[status]) == envelope["summary"][status], status
        assert {row["status"] for row in envelope[status]} <= {status}


def test_every_list_is_there_even_when_empty(tmp_path, sidecar):
    """A key that appears only when non-empty makes every reader write a
    `.get`, and one of them will forget. A passing document has no failures,
    and `fail` is still an empty list."""
    _, envelope = _run(tmp_path, COMPLETE, sidecar)
    assert envelope["fail"] == []
    assert all(status in envelope for status in STATUSES)


def test_the_envelope_carries_no_timestamp(tmp_path, sidecar):
    """Two checks of one unchanged document must produce the same bytes, or a
    caller that commits this could never report it unchanged."""
    _, first = _run(tmp_path, COMPLETE, sidecar)
    _, second = _run(tmp_path, COMPLETE, sidecar)
    assert first == second


def test_every_status_is_counted_even_at_zero(tmp_path, sidecar):
    """A key that appears only when non-zero makes every reader write a
    `.get`, and one of them will forget."""
    _, envelope = _run(tmp_path, COMPLETE, sidecar)
    assert set(envelope["summary"]) == {"total", *STATUSES}


def test_the_envelope_is_written_where_it_was_asked_for(tmp_path, sidecar):
    """Including a directory that does not exist yet, a CI job naming an
    output folder it never created being the normal case."""
    output = tmp_path / "nested" / "deeper" / "qc.json"
    main(
        [
            "--pins",
            str(sidecar),
            "--dmp",
            str(_write(tmp_path / "dmp.json", COMPLETE)),
            "--json",
            str(output),
            "--rules-dir",
            str(RULES_DIR),
        ]
    )
    assert json.loads(output.read_text())["verdict"] == "pass"


# Files from another repository


def test_a_pins_file_that_is_not_there_is_named(tmp_path):
    with pytest.raises(PinsFileError, match="cannot be read"):
        read_pins(tmp_path / "nothing.json")


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param("[]", "not a mapping", id="a list"),
        pytest.param('"glider"', "not a mapping", id="a string"),
        pytest.param("null", "not a mapping", id="empty"),
        pytest.param('{"project": "glider"}', "no 'rules' key", id="no rules key"),
    ],
)
def test_a_pins_file_that_says_nothing_useful_says_why(tmp_path, content, expected):
    """It comes from another repository and no schema validates it on the way
    in, so each way it can fail has to name itself rather than surface as a
    KeyError three frames down."""
    path = tmp_path / "dmp.meta.json"
    path.write_text(content)
    with pytest.raises(PinsFileError, match=expected):
        read_pins(path)


def test_a_pins_file_that_does_not_parse_says_so(tmp_path):
    path = tmp_path / "dmp.meta.json"
    path.write_text("{not json")
    with pytest.raises(PinsFileError, match="does not parse"):
        read_pins(path)


def test_pins_naming_a_version_nobody_wrote_stop_the_run(tmp_path, capsys):
    """Resolving happens before anything is checked, so the run says which
    version is missing instead of writing an envelope about nothing."""
    sidecar = _write(tmp_path / "dmp.meta.json", {"rules": [{"rda_dcs": "9.9.9"}]})
    output = tmp_path / "qc.json"
    code = main(
        [
            "--pins",
            str(sidecar),
            "--dmp",
            str(_write(tmp_path / "dmp.json", COMPLETE)),
            "--json",
            str(output),
            "--rules-dir",
            str(RULES_DIR),
        ]
    )
    assert code == 1
    assert not output.exists()
    assert "9.9.9" in capsys.readouterr().err


def test_a_dmp_that_is_not_json_stops_the_run(tmp_path, sidecar, capsys):
    dmp = tmp_path / "dmp.json"
    dmp.write_text("{not json")
    code = main(
        [
            "--pins",
            str(sidecar),
            "--dmp",
            str(dmp),
            "--json",
            str(tmp_path / "qc.json"),
            "--rules-dir",
            str(RULES_DIR),
        ]
    )
    assert code == 1
    assert "not valid JSON" in capsys.readouterr().err
