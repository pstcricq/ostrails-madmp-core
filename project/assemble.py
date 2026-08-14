"""What a project is made of, assembled once for everyone who builds from it.

A config names the resources its project is built from, and every consumer
needs the same two answers out of them, what the project declares about
itself and what its rules merge into. ``assemble_project()`` gives both, or
raises.

It owns no step of its own, only that they happen in one order, the same for
every caller. There is nothing to merge before the pins resolve.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from configs import load_config_file
from project.merge import Model, merge_rules
from project.pins import resolve_pins

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "rules" / "standards"


@dataclass(frozen=True)
class Project:
    """One project, with every resource it names loaded and valid."""

    # The project config as declared, validated against ``config.schema.json``.
    config: dict[str, Any]
    # Its pinned rules files, merged, base standard first.
    model: Model


def assemble_project(
    config_path: str | Path,
    rules_dir: str | Path = RULES_DIR,
) -> Project:
    """Load one project config and everything it names.

    Three steps: the config is read and validated, its pins are turned into
    paths that exist, and the rules files behind them are merged.

    The resource root is a parameter, defaulting to this repository's tree.

    Raises whatever its steps raise, unchanged, each naming its own kind of
    problem: ``ConfigFileError``, ``UnresolvedPinsError``, ``RulesFileError``,
    ``RulesSetError`` or ``RulesConflictError``.
    """
    config = load_config_file(config_path)
    model = merge_rules(resolve_pins(config["rules"], rules_dir))
    return Project(config=config, model=model)
