"""Pins resolved against the real rules tree, and every way a project can name
something that is not there.

The point of these tests is the message: an unresolved pin is a typo in a
config, and the fix is only obvious if the error names what does exist.
"""

from pathlib import Path

import pytest
import yaml

from project import UnresolvedPinsError, resolve_pins

ROOT = Path(__file__).parent.parent
RULES_DIR = ROOT / "rules" / "standards"
GLIDER_CONFIG = ROOT / "configs" / "projects" / "glider.yaml"


# What a real project declares


def test_the_real_config_resolves():
    """The one test that ties the two data packages together: every pin
    glider.yaml declares names a file that exists."""
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    rules = resolve_pins(config["rules"], RULES_DIR)
    assert [p.relative_to(ROOT).as_posix() for p in rules] == [
        "rules/standards/rda_dcs/1.0.0.json",
        "rules/standards/ostrails/1.0.0.json",
    ]


def test_pin_order_is_kept():
    """Extensions merge in the order they are received, so resolution must
    not sort, the config decides which standard tightens after which."""
    pins = [{"ostrails": "1.0.0"}, {"rda_dcs": "1.0.0"}]
    assert [p.parent.name for p in resolve_pins(pins, RULES_DIR)] == [
        "ostrails",
        "rda_dcs",
    ]


def test_no_pins_resolves_to_no_paths():
    """An empty list is not this module's business to refuse, the config
    schema requires at least one pin."""
    assert resolve_pins([], RULES_DIR) == []


# What a broken project says


def _problems(call) -> str:
    with pytest.raises(UnresolvedPinsError) as excinfo:
        call()
    return str(excinfo.value)


def test_unknown_standard_lists_the_ones_that_exist():
    problems = _problems(lambda: resolve_pins([{"rda-dcs": "1.0.0"}], RULES_DIR))
    assert "unknown standard 'rda-dcs'" in problems
    assert "ostrails, rda_dcs" in problems


def test_unknown_version_lists_the_ones_that_exist():
    problems = _problems(lambda: resolve_pins([{"ostrails": "2.0.0"}], RULES_DIR))
    assert "unknown version '2.0.0'" in problems
    assert "it has 1.0.0" in problems


def test_only_directories_holding_a_versioned_file_are_offered(tmp_path):
    """A directory with nothing of the right kind in it is not a standard,
    `rules/standards/` would otherwise offer `__pycache__` if one appeared."""
    (tmp_path / "ostrails" / "nested").mkdir(parents=True)
    (tmp_path / "ostrails" / "1.0.0.json").write_text("{}")
    (tmp_path / "junk").mkdir()
    problems = _problems(lambda: resolve_pins([{"nope": "1.0.0"}], tmp_path))
    assert "has ostrails." in problems


def test_every_unresolved_pin_reported_at_once():
    """One resolution, one verdict, whatever the number of bad pins."""
    problems = _problems(
        lambda: resolve_pins(
            [{"rda_dcs": "1.0.0"}, {"nope": "1.0.0"}, {"ostrails": "9.9.9"}], RULES_DIR
        )
    )
    assert "3 unresolved pin(s)" not in problems
    assert "2 unresolved pin(s)" in problems
    assert "unknown standard 'nope'" in problems
    assert "unknown version '9.9.9'" in problems


@pytest.mark.parametrize(
    "pin",
    [
        {"ostrails": "../ostrails/1.0.0"},
        {"ostrails": ".."},
        {"ostrails": ""},
        {"../rules/standards/ostrails": "1.0.0"},
    ],
)
def test_a_pin_part_may_not_be_a_path(pin):
    """A version is data that gets built into a path. Left unchecked, one
    carrying a separator reaches outside the resource tree, and the error a
    config author would see would be about a missing version rather than
    about the real mistake."""
    problems = _problems(lambda: resolve_pins([pin], RULES_DIR))
    assert "neither part may be a path" in problems


def test_an_empty_resource_tree_says_nothing_rather_than_an_empty_list(tmp_path):
    problems = _problems(lambda: resolve_pins([{"ostrails": "1.0.0"}], tmp_path))
    assert "has nothing" in problems


def test_a_resource_tree_that_does_not_exist_says_so(tmp_path):
    """Pointing the resolver at the wrong directory is not the config's fault,
    and the message must not read as if it were."""
    problems = _problems(
        lambda: resolve_pins([{"ostrails": "1.0.0"}], tmp_path / "gone")
    )
    assert "no such directory" in problems


def test_a_standard_with_no_versions_says_nothing(tmp_path):
    (tmp_path / "ostrails").mkdir()
    problems = _problems(lambda: resolve_pins([{"ostrails": "1.0.0"}], tmp_path))
    assert "it has nothing" in problems
