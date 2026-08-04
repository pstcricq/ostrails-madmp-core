"""configs/loader.py: every project config in the repository loads clean, the
schema rejects what it is meant to (missing field, unknown field, wrong type),
a config whose filename disagrees with the id it declares is refused, and every
problem of one load is reported in a single error."""

from pathlib import Path

import pytest
import yaml

from configs.loader import ConfigFileError, load_config_file

PROJECTS_DIR = Path(__file__).parent.parent / "configs" / "projects"
REAL_CONFIGS = sorted(PROJECTS_DIR.glob("*.yaml"))


@pytest.mark.parametrize("path", REAL_CONFIGS, ids=lambda p: p.stem)
def test_real_config_loads(path):
    config = load_config_file(path)
    assert config["id"]
    assert config["rules"]


def test_at_least_one_real_config_exists():
    """Guards the parametrized test above: an empty glob would make it pass by
    running zero cases."""
    assert REAL_CONFIGS


def _valid_config(**overrides):
    config = {
        "id": "test-project",
        "name": "Test Project",
        "version": "1.0.0",
        "author": "Someone",
        "license": "CC BY 4.0",
        "rules": [{"rda_dcs": "1.0.0"}],
        "organizationId": "socib",
        "description": "A project used by the tests.",
        "references": [{"label": "Somewhere", "url": "https://example.org"}],
        "auto_timestamps": True,
    }
    config.update(overrides)
    return config


def _write(tmp_path, config, filename=None):
    """Writes at <id>.yaml — load_config_file checks the filename against the
    declared id, so a fixture that wants to exercise anything else must sit
    where it says. ``filename`` overrides it, to break that agreement on
    purpose."""
    stem = filename if filename is not None else config.get("id", "x")
    path = tmp_path / f"{stem}.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def _load_problems(tmp_path, config, filename=None) -> str:
    with pytest.raises(ConfigFileError) as excinfo:
        load_config_file(_write(tmp_path, config, filename))
    return str(excinfo.value)


def test_valid_config_loads(tmp_path):
    assert load_config_file(_write(tmp_path, _valid_config()))["id"] == "test-project"


def test_syntactically_broken_yaml_is_a_config_file_error(tmp_path):
    """A stray bracket must not escape as a raw yaml.YAMLError: callers catch
    ConfigFileError and nothing else."""
    path = tmp_path / "test-project.yaml"
    path.write_text("id: [oops\nname: Test\n")
    with pytest.raises(ConfigFileError, match="invalid YAML"):
        load_config_file(path)


def test_empty_file_rejected(tmp_path):
    """safe_load returns None on an empty file — a non-dict must be rejected by
    the schema, not crash the layout check that follows it."""
    path = tmp_path / "test-project.yaml"
    path.write_text("")
    with pytest.raises(ConfigFileError, match=r"\(root\)"):
        load_config_file(path)


def test_missing_required_field_rejected(tmp_path):
    config = _valid_config()
    del config["rules"]
    assert "rules" in _load_problems(tmp_path, config)


def test_unknown_field_rejected(tmp_path):
    """The schema is closed on purpose. `instruments:` is the case that matters
    today: the concept was dropped, and a config still pinning one must be told
    so rather than have the pin quietly ignored."""
    problems = _load_problems(tmp_path, _valid_config(instruments=[{"x": "1.0.0"}]))
    assert "instruments" in problems


def test_wrong_type_rejected(tmp_path):
    assert "boolean" in _load_problems(tmp_path, _valid_config(auto_timestamps="yes"))


def test_empty_rules_rejected(tmp_path):
    """A config pins at least the base standard; an empty list would merge to
    nothing."""
    assert "rules" in _load_problems(tmp_path, _valid_config(rules=[]))


def test_bare_standard_name_rejected(tmp_path):
    """A rules file is versioned (rules/standards/<standard>/<version>.json), so
    a bare name designates nothing as soon as a second version of it exists."""
    assert "rules" in _load_problems(tmp_path, _valid_config(rules=["rda_dcs"]))


def test_several_extensions_accepted(tmp_path):
    """Nothing caps the number of standards, and the pins keep the order they
    were written in: the base is first because the file says so, not because
    the schema knows which one it is."""
    pins = [{"rda_dcs": "1.0.0"}, {"ostrails": "1.0.0"}, {"other": "2.0.0"}]
    loaded = load_config_file(_write(tmp_path, _valid_config(rules=pins)))
    assert loaded["rules"] == pins


def test_id_pattern_rejected(tmp_path):
    """The id names the KM, the template and the DSW project; it is lowercase
    and dash-separated so those names never depend on how it was typed."""
    assert "id" in _load_problems(tmp_path, _valid_config(id="Test Project"))


def test_empty_human_name_rejected(tmp_path):
    """`name` is free-form — it is prose a reader sees — but a package with a
    blank name is a package nobody can pick out of a DSW list."""
    assert "name" in _load_problems(tmp_path, _valid_config(name=""))


def test_filename_disagreeing_with_id_rejected(tmp_path):
    """Renaming a config without renaming what it declares would publish the
    project somewhere else, silently."""
    problems = _load_problems(tmp_path, _valid_config(), filename="elsewhere")
    assert "id 'test-project'" in problems
    assert "'elsewhere'" in problems


def test_every_problem_reported_at_once(tmp_path):
    """One load, one verdict: fixing a config should not mean rerunning it
    once per mistake."""
    config = _valid_config(auto_timestamps="yes", id="Test Project")
    del config["license"]
    problems = _load_problems(tmp_path, config)
    assert "license" in problems
    assert "boolean" in problems
    assert "id" in problems
