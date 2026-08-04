"""One ``configs/projects/*.yaml`` file, and everything that can be wrong with it.

:func:`load_config_file` is the only entry point — it reads *and* validates in one
step, so a config that reaches a caller is a config that passed. Two layers,
reported together:

1. Structural — against :data:`configs/config.schema.json`, which is strict:
   every field required, none extra. A missing ``rules`` or a ``rule:`` typo
   fails here rather than deep inside generation.
2. Layout — the filename must equal ``id``. A project has one machine name,
   declared once: it is what this file is called (how a config is selected, and
   what CI iterates over), its destination folder in the dmp-registry, and what
   the KM, the template and the DSW project are named after. Declaring it and
   filing it are two ways of saying it, and they agree only by convention:
   renaming the file would silently publish the project somewhere else. The
   check is inside the load rather than beside it, for the reason ``rules``
   gives — a check a caller has to remember to run is a check that gets
   forgotten. ``name`` is not checked against anything: it is prose, and the
   only field a reader ever sees.

Same shape as ``rules/loader.py``: both build on the shared ``utils.schema``
plumbing and add only their own ``…FileError`` subclass, schema file, and
domain checks. Configs need no coherence pass — the schema says it all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from utils.schema import SchemaFileError, schema_problems, validator_for

SCHEMA_PATH = Path(__file__).with_name("config.schema.json")


class ConfigFileError(SchemaFileError):
    """A project config is malformed (schema or layout)."""


def _layout_problems(path: Path, doc: dict[str, Any]) -> list[str]:
    """The ways the file disagrees with the path it sits at: today, only its
    id. Kept as a list so a second check joins the first without changing how
    :func:`load_config_file` reads."""
    identifier = doc["id"]
    if identifier != path.stem:
        return [
            (
                f"declares id {identifier!r} but is filed as {path.stem!r}; "
                f"the two must agree."
            )
        ]
    return []


def load_config_file(path: str | Path) -> dict[str, Any]:
    """Load one project config (YAML), fully validated.

    Returns the parsed document. Raises :class:`ConfigFileError` listing every
    problem found — syntax included, so that one exception type covers every
    way a config can be wrong and callers need catch nothing else.
    """
    try:
        doc = yaml.safe_load(Path(path).read_text())
    except yaml.YAMLError as err:
        raise ConfigFileError(path, [f"invalid YAML: {err}"]) from err
    problems = schema_problems(validator_for(SCHEMA_PATH), doc)
    if not problems and isinstance(doc, dict):
        problems = _layout_problems(Path(path), doc)
    if problems:
        raise ConfigFileError(path, problems)
    return doc
