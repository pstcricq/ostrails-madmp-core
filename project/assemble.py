"""What a project is made of, assembled once for everyone who builds from it.

A config names the resources its project is built from, and every consumer
needs the same two answers out of them: what the project declares about
itself, and what its rules merge into. :func:`assemble_project` gives both, or
raises.

**Both, always**, even for a caller that reads only one. Letting each consumer
assemble the subset it happens to need is exactly how two of them come to
disagree about what "this project" means — the reason pin resolution lives in
:mod:`project.pins` rather than in whichever consumer called for it first.
This module owns no step of its own: it owns that the steps happen, once, in
the same order for everyone.

The order is forced rather than chosen. There is nothing to merge before the
pins resolve, which is the same ordering :mod:`project.merge` imposes on its
own two phases.

Nothing here derives a DSW package identifier, names an output directory, or
knows a registry exists. Those are answers about what gets *generated* from a
project, and they belong with whoever generates.
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
    """One project, with every resource it names loaded and valid.

    Holding the two together is the point: this is the value that travels into
    every builder, and none of them can be handed a half-loaded project.
    """

    #: The project config as declared, validated against ``config.schema.json``.
    config: dict[str, Any]
    #: Its pinned rules files, merged — base standard first.
    model: Model


def assemble_project(
    config_path: str | Path,
    rules_dir: str | Path = RULES_DIR,
) -> Project:
    """Load one project config and everything it names.

    Three steps, none of them owned here: ``configs/`` reads and validates the
    config, :func:`project.pins.resolve_pins` turns its pins into paths that
    exist, and :func:`project.merge.merge_rules` says what the files behind them
    amount to.

    The resource root is a parameter so a test can point at a tree of its own,
    and defaults to this repository's — the only one a real run ever uses.

    Raises whatever its steps raise, unchanged, each already naming its own
    kind of problem: :class:`configs.ConfigFileError` for the config,
    :class:`project.pins.UnresolvedPinsError` for a pin naming a file that is
    not there, :class:`rules.RulesFileError` for a malformed rules file, and
    :class:`project.merge.RulesSetError` / :class:`project.merge.
    RulesConflictError` for a set of them that does not hold together.
    """
    config = load_config_file(config_path)
    model = merge_rules(resolve_pins(config["rules"], rules_dir))
    return Project(config=config, model=model)
