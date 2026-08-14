"""The door to a project's resources: what it hands back, and what it refuses.

Two things. First, that a real config comes back as the answers a builder
asks of it. Second, that it is all of them or none, a project whose resources
do not all resolve must not come back holding the ones that did.
"""

from pathlib import Path

import pytest
import yaml

from configs import ConfigFileError
from project import UnresolvedPinsError, assemble_project

ROOT = Path(__file__).parent.parent
RULES_DIR = ROOT / "rules" / "standards"
GLIDER_CONFIG = ROOT / "configs" / "projects" / "glider.yaml"


def _config(tmp_path: Path, **overrides) -> Path:
    """The real config with something changed, written where its own layout
    check accepts it, the filename must be the id it declares."""
    doc = yaml.safe_load(GLIDER_CONFIG.read_text())
    doc.update(overrides)
    path = tmp_path / f"{doc['id']}.yaml"
    path.write_text(yaml.safe_dump(doc))
    return path


# What a real project comes back as


def test_the_real_project_loads():
    project = assemble_project(GLIDER_CONFIG)
    assert project.config["id"] == "glider"
    assert project.model.standards == ("rda_dcs", "ostrails")


def test_the_model_carries_the_versions_the_config_pins():
    """The merged model carries the very versions the config named, in the
    order it named them, not whatever is latest on disk."""
    project = assemble_project(GLIDER_CONFIG)
    pinned = [version for pin in project.config["rules"] for version in pin.values()]
    assert [version for _, version in project.model.standard_versions] == pinned


def test_the_config_comes_back_unchanged(tmp_path):
    """The door composes, it does not reshape, the config comes back field
    for field."""
    project = assemble_project(GLIDER_CONFIG)
    assert project.config == yaml.safe_load(GLIDER_CONFIG.read_text())


def test_a_project_is_frozen():
    """The value travels into every builder, and none of them gets to edit
    it for the others."""
    project = assemble_project(GLIDER_CONFIG)
    with pytest.raises(AttributeError):
        project.config = {}


# All of it, or none of it


def test_a_missing_rules_version_stops_the_load(tmp_path):
    """The invariant of the door. One pin of this config resolves perfectly
    well, the project is still broken, and no caller sees half of it."""
    config = _config(tmp_path, rules=[{"rda_dcs": "1.0.0"}, {"ostrails": "9.9.9"}])
    with pytest.raises(UnresolvedPinsError) as excinfo:
        assemble_project(config)
    assert "unknown version '9.9.9'" in str(excinfo.value)


def test_a_malformed_config_stays_the_config_package_s_error(tmp_path):
    """Every step keeps its own error type. The door adds none of its own
    and wraps none of theirs, so a failure says which layer found it."""
    doc = yaml.safe_load(GLIDER_CONFIG.read_text())
    del doc["rules"]
    path = tmp_path / "glider.yaml"
    path.write_text(yaml.safe_dump(doc))
    with pytest.raises(ConfigFileError):
        assemble_project(path)


def test_the_rules_root_is_a_parameter(tmp_path):
    """A test points the door at a tree of its own, a real run never does."""
    with pytest.raises(UnresolvedPinsError, match="no such directory"):
        assemble_project(GLIDER_CONFIG, rules_dir=tmp_path / "gone")
