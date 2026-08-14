"""One ``configs/projects/*.yaml`` file, and everything that can be wrong with it.

``load_config_file()`` is the only entry point. It validates in two layers,
and a failing layer reports every problem it found rather than the first one:

1. Structural, against ``config.schema.json``, which is strict: every field
   required, none extra.
2. Layout, only once the schema passed: the filename must equal the declared
   ``id``.

``name`` is checked against nothing, it is prose.
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
    """Every way the file disagrees with the path it sits at, at once.

    Today that is only the declared ``id`` against the filename, returned as a
    list so a second check can join it.
    """
    identifier = doc["id"]
    if identifier != path.stem:
        return [
            (
                f"declares id {identifier!r} but is filed as {path.stem!r}, "
                f"the two must agree."
            )
        ]
    return []


def load_config_file(path: str | Path) -> dict[str, Any]:
    """Load one project config (YAML), fully validated.

    Returns the parsed document. Raises ``ConfigFileError`` listing every
    problem found, an unreadable path and a syntax error included, so a caller
    needs to catch nothing else.
    """
    try:
        doc = yaml.safe_load(Path(path).read_text())
    except OSError as err:
        raise ConfigFileError(path, [f"cannot be read: {err.strerror}."]) from err
    except yaml.YAMLError as err:
        raise ConfigFileError(path, [f"invalid YAML: {err}"]) from err
    # The layout check reads doc["id"] unguarded, which the schema pass has
    # just guaranteed to be there and typed, so it only runs when that pass
    # found nothing. An empty file, where safe_load returns None, fails the
    # schema as a non-object.
    problems = schema_problems(validator_for(SCHEMA_PATH), doc)
    if not problems:
        problems = _layout_problems(Path(path), doc)
    if problems:
        raise ConfigFileError(path, problems)
    return doc
