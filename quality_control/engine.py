"""Check one DMP document against the merged rules ``Model``.

``run_qc()`` walks the model tree and the document together, once, and returns
a flat list of ``CheckResult``, plain data with nothing of a runner or a
report in it.

Four statuses:

- ``fail``    : a real violation, a required field missing, a JSON shape the
                cardinality does not allow, a wrong type or format, a value
                outside a strict ``allowed_values`` vocabulary, or a key no
                rule declares
- ``missing`` : an optional field is absent, which follows from cardinality
                alone and is never an error
- ``warning`` : a present value outside a recommended ``suggested_values``
                vocabulary, the only source of warnings
- ``pass``    : present and valid

There is one PASS/FAIL rule, ``has_failures()``: a document fails when at
least one check does.

(!!) An empty string counts as an absence, not a value. The document template
emits every required scalar unconditionally, so ``""`` is what an unanswered
question renders as, and reading it as a value would have a required field
nobody answered pass both its presence and its type check. A string of spaces
stays a value, that is content someone typed.

Categories: ``structure`` for the document holding a ``dmp`` object, then per
field ``presence`` and ``shape``, and per present scalar value ``type``,
``allowed_values`` and ``suggested_values``. ``unexpected`` asks the question
the other way round, a key the document carries that no rule declares.

Where a constraint was imposed by an extension rather than the base standard,
the message says so, from the tightenings the model records.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from project import Field, Model

# Every ``_type`` a rules file may declare for a scalar. ``object`` is not one
# of them, it is a container the walk recurses into.
SCALAR_TYPES = (
    "string",
    "number",
    "boolean",
    "date",
    "datetime",
    "email",
    "url",
    "currency",
    "country_code",
    "language",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LANGUAGE_RE = re.compile(r"^[a-z]{3}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://\S+$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")


@dataclass(frozen=True)
class CheckResult:
    """One check on one concrete value, or absence, in the document."""

    # structure, presence, shape, type, allowed_values, suggested_values,
    # unexpected
    category: str
    status: str  # pass | fail | warning | missing
    rule_path: str  # the rule checked, e.g. "dmp.dataset[].distribution[].title"
    instance_path: str  # the concrete spot, e.g. "dmp.dataset[0].distribution[2].title"
    standard: str  # the standard that introduced the field
    message: str


def results_to_dicts(results: list[CheckResult]) -> list[dict[str, Any]]:
    """JSON-ready view of the results."""
    return [asdict(r) for r in results]


def has_failures(results: Iterable[CheckResult]) -> bool:
    """Whether any check is a real violation, which is the whole PASS/FAIL
    rule."""
    return any(r.status == "fail" for r in results)


# Scalar type and format checks


def _check_scalar_type(value: Any, value_type: str) -> tuple[bool, str]:
    """Whether one value matches its declared scalar type, and what to say
    when it does not."""
    if value_type == "string":
        return isinstance(value, str), "expected a string"
    if value_type == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        return ok, "expected a number"
    if value_type == "boolean":
        return isinstance(value, bool), "expected a boolean"
    if value_type == "date":
        if not isinstance(value, str):
            return False, "expected an ISO 8601 date string (YYYY-MM-DD)"
        # The pattern first, `date.fromisoformat` also accepting forms this
        # does not mean, YYYYMMDD and week dates among them. Then the parse,
        # which is what rejects a day the calendar does not have.
        if _DATE_RE.match(value):
            try:
                date.fromisoformat(value)
                return True, ""
            except ValueError:
                pass
        return False, f"{value!r} is not a valid ISO 8601 date (YYYY-MM-DD)"
    if value_type == "datetime":
        if not isinstance(value, str):
            return False, "expected an ISO 8601 datetime string"
        try:
            datetime.fromisoformat(value)
            return True, ""
        except ValueError:
            return False, f"{value!r} is not a valid ISO 8601 datetime"
    if value_type == "language":
        ok = isinstance(value, str) and bool(_LANGUAGE_RE.match(value))
        return ok, f"{value!r} is not an ISO 639-3 language code (3 lowercase letters)"
    if value_type == "email":
        ok = isinstance(value, str) and bool(_EMAIL_RE.match(value))
        return ok, f"{value!r} is not a valid email address"
    if value_type == "currency":
        ok = isinstance(value, str) and bool(_CURRENCY_RE.match(value))
        return ok, f"{value!r} is not an ISO 4217 currency code (3 uppercase letters)"
    if value_type == "country_code":
        ok = isinstance(value, str) and bool(_COUNTRY_CODE_RE.match(value))
        return ok, f"{value!r} is not an ISO 3166-1 alpha-2 country code"
    if value_type == "url":
        ok = isinstance(value, str) and bool(_URL_RE.match(value))
        return ok, f"{value!r} is not a valid URL"
    raise ValueError(f"Unknown scalar type: {value_type}")


# Walking the model and the document together


def _tightening_note(field: Field, aspect: str) -> str:
    """A parenthesised provenance note when an extension tightened this
    aspect, empty otherwise."""
    for tightening in field.tightenings:
        if tightening.aspect == aspect:
            if aspect == "cardinality":
                return (
                    f" (required by {tightening.standard}, "
                    f"{tightening.before} in {field.origin})"
                )
            return f" (restricted by {tightening.standard})"
    return ""


def _unexpected_keys(
    container: dict,
    known: tuple[Field, ...],
    instance_path: str,
    rule_path: str,
    standard: str,
) -> Iterator[CheckResult]:
    """Every key of one concrete object that matches no declared field.

    The only check that reads the document rather than the model, so it is
    also the only one that can catch a key nothing else will ever look at.
    """
    names = {child.name for child in known}
    for key in container:
        if key in names:
            continue
        yield CheckResult(
            "unexpected",
            "fail",
            f"{rule_path}.{key}",
            f"{instance_path}.{key}",
            standard,
            f"'{instance_path}.{key}' is not a field the merged rules declare. "
            f"Check the spelling, or whether it belongs to a standard this "
            f"project does not pin.",
        )


def _check_value(field: Field, value: Any, instance_path: str) -> Iterator[CheckResult]:
    """Checks on one present, non-list value of `field`: its shape, and for a
    scalar its type and vocabularies. Recurses into an object's children."""

    def result(category: str, status: str, message: str) -> CheckResult:
        return CheckResult(
            category, status, field.dotted_path, instance_path, field.origin, message
        )

    if field.type == "object":
        if not isinstance(value, dict):
            yield result(
                "shape",
                "fail",
                f"'{instance_path}' should be an object ({{}}) but is "
                f"{type(value).__name__}.",
            )
            return
        yield result("shape", "pass", f"'{instance_path}' is an object, as expected.")
        yield from _unexpected_keys(
            value, field.children, instance_path, field.dotted_path, field.origin
        )
        for child in field.children:
            yield from _visit(child, value, instance_path)
        return

    if isinstance(value, (dict, list)):
        yield result(
            "shape",
            "fail",
            f"'{instance_path}' should be a scalar value but is "
            f"{'an object' if isinstance(value, dict) else 'a list'}.",
        )
        return
    yield result("shape", "pass", f"'{instance_path}' is a single value, as expected.")

    ok, problem = _check_scalar_type(value, field.type)
    yield result(
        "type",
        "pass" if ok else "fail",
        f"'{instance_path}' is a valid {field.type}."
        if ok
        else f"'{instance_path}': {problem}.",
    )

    if field.allowed_values is not None:
        if value in field.allowed_values:
            yield result(
                "allowed_values",
                "pass",
                f"'{instance_path}' = {value!r} is an allowed value.",
            )
        else:
            yield result(
                "allowed_values",
                "fail",
                f"'{instance_path}' = {value!r} is not one of the allowed values "
                f"{list(field.allowed_values)}"
                f"{_tightening_note(field, 'allowed_values')}.",
            )

    if field.suggested_values is not None:
        if value in field.suggested_values:
            yield result(
                "suggested_values",
                "pass",
                f"'{instance_path}' = {value!r} matches the suggested values.",
            )
        else:
            yield result(
                "suggested_values",
                "warning",
                f"'{instance_path}' = {value!r} is not one of the suggested values "
                f"{list(field.suggested_values)}"
                f"{_tightening_note(field, 'suggested_values')}.",
            )


def _visit(field: Field, container: dict, parent_path: str) -> Iterator[CheckResult]:
    """All checks for `field` inside one concrete parent object, recursing
    into descendants.

    An absent or empty field yields exactly one presence result and nothing
    underneath, so an unanswered optional object says one thing rather than
    one per field it would have held.
    """
    value = container.get(field.name)
    instance_path = f"{parent_path}.{field.name}"

    def result(category: str, status: str, message: str) -> CheckResult:
        return CheckResult(
            category, status, field.dotted_path, instance_path, field.origin, message
        )

    if value is None or value == "" or (field.is_list and value == []):
        if field.is_required:
            what = "is missing" if value is None else "is empty"
            yield result(
                "presence",
                "fail",
                f"Required field '{instance_path}' (cardinality "
                f"{field.cardinality}) {what}"
                f"{_tightening_note(field, 'cardinality')}.",
            )
        else:
            yield result(
                "presence", "missing", f"Optional field '{instance_path}' is absent."
            )
        return

    yield result("presence", "pass", f"'{instance_path}' is present.")

    if field.is_list:
        if not isinstance(value, list):
            yield result(
                "shape",
                "fail",
                f"'{instance_path}' should be a list (cardinality "
                f"{field.cardinality}) but is {type(value).__name__}.",
            )
            return
        yield result(
            "shape",
            "pass",
            f"'{instance_path}' is a list of {len(value)}, as expected.",
        )
        for index, item in enumerate(value):
            yield from _check_value(field, item, f"{instance_path}[{index}]")
        return

    if isinstance(value, list):
        yield result(
            "shape",
            "fail",
            f"'{instance_path}' should be a single value (cardinality "
            f"{field.cardinality}) but is a list.",
        )
        return
    yield from _check_value(field, value, instance_path)


def run_qc(model: Model, document: Any) -> list[CheckResult]:
    """Check `document`, a parsed DMP JSON, against `model`.

    Always starts with one ``structure`` result: the document must be an
    object holding a ``dmp`` object. Without that there is nothing to walk,
    so it is also the only result in that case.
    """
    dmp = document.get("dmp") if isinstance(document, dict) else None
    if not isinstance(dmp, dict):
        return [
            CheckResult(
                "structure",
                "fail",
                "dmp",
                "dmp",
                model.base_standard,
                "Document has no top-level 'dmp' object, nothing to check.",
            )
        ]

    results = [
        CheckResult(
            "structure",
            "pass",
            "dmp",
            "dmp",
            model.base_standard,
            "Top-level 'dmp' object found.",
        )
    ]
    results.extend(
        _unexpected_keys(dmp, model.fields, "dmp", "dmp", model.base_standard)
    )
    for field in model.fields:
        results.extend(_visit(field, dmp, "dmp"))
    return results
