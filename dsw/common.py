"""What two modules of this package must answer identically.

Three modules turn one project into what DSW consumes — two generators and the
publisher — and each pair of them has something it may not disagree about. The
generators reference each other's entities, so they agree question by question
on what a rules field becomes: :func:`field_kind` and
:func:`needs_a_synthetic_escape` are that agreement, and a field the KM asks as
a list while the template renders a single value is a pair of packages that
cannot be filled. The publisher never meets a rules field, but it has to find
on disk exactly what a generator wrote, so :func:`km_path` and
:func:`template_path` are that agreement.

**The rule this module refuses an addition by:** something here is answered the
same way by more than one module *and* would be a fault if they diverged.
Something one module alone uses belongs in that module, however tempting the
name of this one.

Nothing here reads or writes a file, and nothing here reaches an instance.
Loading is ``project/``'s job, writing is a generator's, uploading is
``publish.py``'s; what is left in between is decisions.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project import Field, Model

# Every generated artifact lands under build/, one subdirectory per kind. CI
# uploads that directory as a workflow artifact, and `publish.py` reads it back
# — which is the whole reason the two functions below exist rather than each
# module spelling a path of its own.
BUILD_DIR = Path(__file__).resolve().parents[1] / "build"

# The dmp fields filled from the render context instead of a reply. `created`
# and `modified` are opt-in per project through `auto_timestamps`; `dmp_id` is
# always computed, its value coming entirely from the context.
_TIMESTAMP_FIELDS = {"created", "modified"}
_DMP_ID_FIELD = {"dmp_id"}

# What a vocabulary calls "none of those listed", compared case-insensitively
# so that RDA DCS's `other` and DataCite's `Other` are one convention. Written
# here rather than declared per rules file: no file needs to say it yet, and a
# second way to spell one convention is what this is here to prevent.
ESCAPE_VALUE = "other"


def km_path(project_id: str) -> Path:
    """Where a project's Knowledge Model bundle is written, and therefore
    where it is read back from.

    One generator writes it and the publisher looks for it, in different runs
    and — in CI — on different machines through an uploaded artifact. Each
    spelling its own path would not fail on the day they diverge but on the
    first publish afterwards, as "not found: run dsw.generate_km first", which
    is the one thing that would not have gone wrong.
    """
    return BUILD_DIR / "km" / f"{project_id}_km.km"


def template_path(project_id: str) -> Path:
    """Where a project's Document Template bundle is written and read back.
    See :func:`km_path`."""
    return BUILD_DIR / "template" / f"{project_id}_template.json"


def package_id(config: dict[str, Any]) -> str:
    """The DSW package identifier of a project — the one name its KM and its
    template each carry, which is how DSW knows they belong together. Derived
    rather than declared: three fields the config already states, in the order
    DSW reads them."""
    return "{organizationId}:{id}:{version}".format(**config)


def utc_timestamp() -> str:
    """The creation timestamp stamped on every generated event and bundle."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def standard_label(standard: str) -> str:
    """A standard's name as a reader sees it: ``rda_dcs`` -> ``RDA_DCS``.

    A standard has one spelling in code — snake_case, from the directory name
    to the config pin to a field's ``origin`` — and the displayable form is
    derived here, at the point of display, rather than declared beside it. A
    declared label would be a second name for one thing, free to drift from
    the first.

    In ``common`` rather than in ``utils/``: that package takes what at least
    two packages import, and every caller today is a generator. Which is what
    this module means.
    """
    return standard.upper()


def needs_a_synthetic_escape(field: Field) -> bool:
    """Whether the generators must add an "Other" answer of their own beside a
    field's declared values, opening a free-text follow-up.

    Only where the vocabulary admits values it does not list, *and* names no
    escape of its own. RDA DCS and DataCite both end several vocabularies with
    one — spelled ``other`` by the first, ``Other`` by the second — and neither
    gives a field beside it to say which value was meant. It is a value, not a
    door, and a field that has one does not get a second: two escapes for one
    notion is how the declared value came to be dropped from the list a
    researcher is shown.

    Here rather than in either generator because both must answer it the same
    way. On a vocabulary spelling it in lower case they have no choice: a UUID
    derives from the value, so the declared answer and the synthetic one *are*
    the same entity, and only one of them can be emitted.
    """
    if field.allowed_values is not None:
        return False
    if field.suggested_values is None:
        return False
    return not any(value.lower() == ESCAPE_VALUE for value in field.suggested_values)


def computed_fields_from_config(config: dict[str, Any]) -> set[str]:
    """Top-level fields the template fills instead of asking: always
    ``dmp_id`` — its identifier is the DMP's own DSW URL, resolved from the
    render context, and rewritten to the dmp-registry location by the
    submission webhook — plus ``created`` and ``modified`` under
    ``auto_timestamps``."""
    computed = set(_DMP_ID_FIELD)
    if config.get("auto_timestamps"):
        computed |= _TIMESTAMP_FIELDS
    return computed


def top_level_split(model: Model) -> tuple[list[Field], list[Field]]:
    """Split the top-level ``dmp`` fields into the general chapter and the
    fields that become chapters of their own.

    A top-level field earns its own chapter exactly when it is an object,
    single or list; every scalar joins the shared general chapter.

    A split, not a filter: nothing is dropped, because the rules are the whole
    questionnaire and every field they declare is asked. Only computed fields
    are skipped, and each generator does that itself.
    """
    general, chapters = [], []
    for field in model.fields:
        (chapters if field.type == "object" else general).append(field)
    return general, chapters


#: Every value :func:`field_kind` can return. A generator dispatches on the
#: kind and must name each of these, refusing what it does not know instead of
#: falling through to a default — a kind added here and forgotten in one
#: generator would otherwise be emitted as something else, quietly, and the
#: pair would be unfillable with nothing red to show for it.
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
    """What DSW entity a rules field becomes — the single decision every
    generator defers to, so that none of them can disagree.

    One of :data:`FIELD_KINDS`: ``"list"`` is a list of objects,
    ``"object_gated"`` a ``0..1`` object behind a Yes/No gate, and
    ``"value_multi"`` a scalar repeated through its cardinality.
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


def readme_tail(config: dict[str, Any], compatibility_lines: list[str]) -> list[str]:
    """The Markdown lines every package README ends with."""
    lines = [
        "## Compatibility",
        "",
        *compatibility_lines,
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
    """One README line naming the exact rules versions merged into this
    artifact — the provenance a QC run reproduces from the same pins."""
    parts = ", ".join(
        f"{standard_label(name)} {version}" for name, version in model.standard_versions
    )
    return f"- Rules: {parts}"


def strip_markdown(text: str) -> str:
    """Markdown reduced to its plain-text reading. DSW renders a package's
    ``readme`` as Markdown but its ``description`` as plain text, and both are
    written once, in the config's prose."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", text)
    return text
