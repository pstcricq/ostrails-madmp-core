"""What two modules of this package must answer identically.

Three modules turn one project into what DSW consumes, two generators and the
publisher, and each pair of them has something it may not disagree about. The
generators agree on what a rules field becomes, ``field_kind()`` and
``needs_a_synthetic_escape()``. The publisher has to find on disk exactly what
a generator wrote, ``km_path()`` and ``template_path()``, and to name one of
the output formats the template bundle carries, ``SUBMISSION_FORMAT`` and
``format_uuid()``.

One condition for something to belong here: it is answered the same way by
more than one module and would be a fault if they diverged. What one module
alone uses belongs in that module.

Nothing here reads or writes a file, and nothing here reaches an instance.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dsw.uuids import u
from project import Field, Model

# Every generated artifact lands under build/, one subdirectory per kind.
BUILD_DIR = Path(__file__).resolve().parents[1] / "build"

# The dmp fields filled from the render context instead of a reply. ``created``
# and ``modified`` are opt-in per project through ``auto_timestamps``, ``dmp_id`` is
# always computed, its value coming entirely from the context.
_TIMESTAMP_FIELDS = {"created", "modified"}
_DMP_ID_FIELD = {"dmp_id"}

# What a vocabulary calls "none of those listed", compared case-insensitively
# so that RDA DCS's ``other`` and DataCite's ``Other`` are one convention.
ESCAPE_VALUE = "other"


def km_path(project_id: str) -> Path:
    """Where a project's Knowledge Model bundle is written, and therefore
    where it is read back from."""
    return BUILD_DIR / "km" / f"{project_id}_km.km"


def template_path(project_id: str) -> Path:
    """Where a project's Document Template bundle is written and read back.
    See ``km_path()``."""
    return BUILD_DIR / "template" / f"{project_id}_template.json"


def format_uuid(name: str) -> str:
    """The DSW uuid of one output format of a project's document template."""
    return u("template", "format", name)


# The format a submitted document is rendered in. ``generate_template`` emits
# a DSW format under this name and ``publish`` names that format's uuid in the
# submission service, so both read it here.
SUBMISSION_FORMAT = "JSON"


def package_id(config: dict[str, Any]) -> str:
    """The DSW package identifier of a project, the one name its KM and its
    template each carry, which is how DSW knows they belong together."""
    return "{organizationId}:{id}:{version}".format(**config)


def utc_timestamp() -> str:
    """The creation timestamp stamped on every generated event and bundle."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def standard_label(standard: str) -> str:
    """A standard's name as a reader sees it, ``rda_dcs`` -> ``RDA_DCS``.

    Derived at the point of display rather than declared beside the standard,
    so a standard keeps one spelling in code.
    """
    return standard.upper()


def needs_a_synthetic_escape(field: Field) -> bool:
    """Whether the generators must add an "Other" answer of their own beside a
    field's declared values, opening a free-text follow-up.

    Only where the vocabulary admits values it does not list, and names no
    escape of its own. RDA DCS and DataCite both end several vocabularies with
    one, spelled ``other`` and ``Other``, and a field that has one does not get
    a second: a UUID derives from the value, so the declared answer and the
    synthetic one would be the same entity.
    """
    if field.allowed_values is not None:
        return False
    if field.suggested_values is None:
        return False
    return not any(value.lower() == ESCAPE_VALUE for value in field.suggested_values)


def computed_fields_from_config(config: dict[str, Any]) -> set[str]:
    """Top-level fields the template fills instead of asking, always
    ``dmp_id``, whose value comes from the render context, plus ``created``
    and ``modified`` under ``auto_timestamps``."""
    computed = set(_DMP_ID_FIELD)
    if config.get("auto_timestamps"):
        computed |= _TIMESTAMP_FIELDS
    return computed


def top_level_split(model: Model) -> tuple[list[Field], list[Field]]:
    """Split the top-level ``dmp`` fields into the general chapter and the
    fields that become chapters of their own.

    A top-level field earns its own chapter exactly when it is an object,
    single or list, every scalar joins the shared general chapter. A split,
    not a filter, nothing is dropped here.
    """
    general, chapters = [], []
    for field in model.fields:
        (chapters if field.type == "object" else general).append(field)
    return general, chapters


# Every value field_kind() can return. A generator dispatches on the kind and
# must name each of these, refusing what it does not know rather than falling
# through to a default.
FIELD_KINDS = (
    "computed",
    "list",
    "object_gated",
    "object_inline",
    "options_strict",
    "options_suggested",
    "options_strict_multi",
    "options_suggested_multi",
    "boolean",
    "value",
    "value_multi",
)


def field_kind(field: Field, computed_fields: set[str]) -> str:
    """What DSW entity a rules field becomes.

    One of ``FIELD_KINDS``: ``"list"`` is a list of objects, ``"object_gated"``
    a ``0..1`` object behind a Yes/No gate, and ``"value_multi"`` a scalar
    repeated through its cardinality.
    """
    if len(field.path) == 1 and field.name in computed_fields:
        return "computed"
    if field.type == "object":
        if field.is_list:
            return "list"
        return "object_gated" if field.cardinality == "0..1" else "object_inline"
    multi = field.is_list
    if field.allowed_values is not None:
        return "options_strict_multi" if multi else "options_strict"
    if field.suggested_values is not None:
        return "options_suggested_multi" if multi else "options_suggested"
    if field.type == "boolean":
        return "boolean"
    return "value_multi" if multi else "value"


def readme_head(config: dict[str, Any], kind: str) -> list[str]:
    """The Markdown lines every package README opens with."""
    return [f"# {config['name']} : {kind}", "", config["description"], ""]


def readme_tail(config: dict[str, Any], compatibility: list[str]) -> list[str]:
    """The Markdown lines every package README ends with.

    ``compatibility`` is a list of plain facts, one per line, and the bullets
    are put on here.
    """
    lines = [
        "## Compatibility",
        "",
        *(f"- {fact}" for fact in compatibility),
        "",
        "## Author",
        "",
        f"Developed by: **{config['author']}**",
        "",
        "## References",
        "",
    ]
    lines += [f"- [{ref['label']}]({ref['url']})" for ref in config["references"]]
    return lines


def rules_provenance_line(model: Model) -> str:
    """One README fact naming the exact rules versions merged into this
    artifact. A fact, not a line, ``readme_tail()`` puts the bullet on."""
    parts = ", ".join(
        f"{standard_label(name)} {version}" for name, version in model.standard_versions
    )
    return f"Rules: {parts}"


def strip_markdown(text: str) -> str:
    """Markdown reduced to its plain-text reading. DSW renders a package's
    ``readme`` as Markdown but its ``description`` as plain text, and both are
    written once, in the config's prose."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    return text
