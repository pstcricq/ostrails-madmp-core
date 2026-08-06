"""Document Template generator: a merged rules model -> a DSW template bundle.

Emits a Jinja2 Document Template producing a plain JSON export. DSW renders it
against a project's replies to produce the final maDMP JSON document.

Every question UUID it references comes from :mod:`dsw.uuids`, applied to the
same merged model :mod:`dsw.generate_km` walks. Never write a UUID by hand
here, and never copy one out of a published KM: deriving them is the whole
reason the template and its KM stay in step.

Conventions in the generated Jinja:

- ``sv(path)`` / ``av(path, default)`` / ``jv(path)`` macros over
  ``r = ctx.project.replies``, plus DSW's own ``reply_path`` /
  ``reply_str_value`` / ``reply_items`` filters.
- ``js(text)`` escapes a string for the inside of a JSON one, and **everything
  that renders text goes through it** — ``jv`` is ``js`` over a reply, and a
  vocabulary label read through ``av`` is wrapped in it at the point it is
  emitted. ``sv`` and ``av`` are the raw readers, left for the comparisons that
  need the value itself and never for output. The document is assembled as
  literal JSON text, so this macro is the whole of what stands between a reply
  and the file.
- The output is assembled as literal JSON text: every key carries its comma in
  front of it and each optional one is wrapped in its own ``{%- if ... %}``
  block, so an object's body is captured and its first comma stripped at render
  time. **No key has to be unconditional** — an object whose fields are all
  optional is a shape a standard may declare, and closing it is the
  generator's problem, not the rules'. See ``doc.md`` ("Le template de
  document").
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dsw.common import (
    SUBMISSION_FORMAT,
    computed_fields_from_config,
    field_kind,
    format_uuid,
    needs_a_synthetic_escape,
    package_id,
    readme_head,
    readme_tail,
    rules_provenance_line,
    standard_label,
    strip_markdown,
    template_path,
    top_level_split,
    utc_timestamp,
)
from dsw.uuids import (
    answer_uuid,
    chapter_uuid,
    gate_uuid,
    gate_yes_uuid,
    list_item_value_uuid,
    other_answer_uuid,
    other_followup_uuid,
    question_uuid,
    u,
)
from project import Field, Project, assemble_project

# The DSW document-template metamodel version — a separate concept from the
# KM's own metamodelVersion (20). Tied to the DSW instance, not the project.
TEMPLATE_METAMODEL_VERSION = "18.0"

# The Jinja expression for each computed top-level field: their value never
# comes from a reply. A computed field with no mapping here is simply absent
# from the document, which matches the KM emitting no question for it.
COMPUTED_FIELD_EXPR: dict[str, str] = {
    "created": "ctx.project.createdAt",
    "modified": "ctx.project.updatedAt",
}

# Every output format this template knows of, implemented or not: one source
# for both the bundle's `formats` (only `available` entries become a real DSW
# format) and the README's table.
FORMATS: list[dict[str, Any]] = [
    {
        # Named from `common` rather than spelt here: this is the format the
        # submission service points at, and `publish` has to name the same one.
        "name": SUBMISSION_FORMAT,
        "available": True,
        "content_type": "application/json",
        "extension": "json",
        "notes": (
            "Plain JSON export of the `dmp` object, following the merged "
            "rules.json schema."
        ),
    },
    {
        "name": "JSON-LD",
        "available": False,
        "content_type": None,
        "extension": None,
        "notes": "Linked-data version of the same output. Not implemented yet.",
    },
]


def reply_path_expr(chain: list[str]) -> str:
    """The Jinja ``|reply_path`` expression for a chain of UUID expressions
    (quoted literals or variable names)."""
    return "[" + ", ".join(chain) + "]|reply_path"


def q(text: str) -> str:
    """``text`` as a Jinja string literal.

    Jinja decodes a literal with ``unicode-escape``, so a backslash, a quote of
    its own and any control character have to be written as escapes. A UUID
    comes through untouched — nothing in one needs escaping — and a vocabulary
    label does not: ``Institut d'Optique`` closed its literal early and left
    the whole template unparsable, which DSW only finds out at render time, in
    front of a researcher.

    One function for both, rather than a safe one beside a fast one: a second
    way to write a Jinja string is a second place for a label to end up in the
    wrong one.
    """
    escaped = text.replace("\\", "\\\\").replace("'", "\\'")
    return "'" + "".join(c if c >= " " else f"\\u{ord(c):04x}" for c in escaped) + "'"


# What a JSON string may not carry unescaped: a backslash, a double quote, and
# every character below U+0020. The backslash comes first — escaping it after
# the others would escape the backslashes the others just produced.
#
# Written out rather than deferred to Jinja's `tojson`, which is HTML-safe as
# well: it escapes the ampersand and the apostrophe to their \u form too, and a
# maDMP is committed to the registry to be read and diffed. Both are ordinary
# in an institution's name.
_JSON_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", "\\\\"),
    ('"', '\\"'),
    ("\b", "\\b"),
    ("\f", "\\f"),
    ("\n", "\\n"),
    ("\r", "\\r"),
    ("\t", "\\t"),
    *(
        (chr(code), f"\\u{code:04x}")
        for code in range(0x20)
        if chr(code) not in "\b\f\n\r\t"
    ),
)


def _json_escape_chain(expression: str) -> str:
    """``expression`` followed by the ``|replace`` chain that turns whatever it
    evaluates to into the body of a JSON string."""
    return expression + "".join(
        f"\n  |replace({q(search)}, {q(replacement)})"
        for search, replacement in _JSON_ESCAPES
    )


class OutputField:
    """One emitted JSON ``"key": value`` pair of the output template.

    ``required`` keys are always emitted; optional keys are each wrapped in
    their own ``{%- if condition %}`` block. Both carry their separating comma
    **in front of them**, and :func:`render_object` strips the one that ends up
    first — so which keys render is decided at render time and no key has to be
    there for the others to hang off.

    ``is_object`` marks ``value_expr`` as raw JSON/Jinja text rather than a
    scalar to quote, and ``preamble`` holds the ``{% set %}`` statements that
    must run before ``condition`` is evaluated.
    """

    def __init__(
        self,
        key: str,
        value_expr: str,
        required: bool,
        condition: str | None = None,
        is_object: bool = False,
        preamble: str = "",
    ) -> None:
        self.key = key
        self.value_expr = value_expr
        self.required = required
        self.condition = condition
        self.is_object = is_object
        self.preamble = preamble

    def render(self, depth: int) -> str:
        """Render as an indented fragment, comma first. For object and array
        values the caller must have built ``value_expr`` with ``depth + 1`` for
        its children — see :func:`render_object`."""
        indent = "  " * depth
        v = self.value_expr if self.is_object else f'"{{{{ {self.value_expr} }}}}"'
        line = f'{indent}"{self.key}": {v}'
        if self.required:
            return f"{self.preamble},\n{line}"
        return f"{self.preamble}{{%- if {self.condition} %}},\n{line}\n{{%- endif %}}"


def object_var(path: tuple[str, ...]) -> str:
    """The Jinja variable an object's body is captured in, ``()`` being the
    ``dmp`` root.

    The leading underscore keeps it out of the way of the item variables built
    from a field path, which start with a letter because a rules field name
    does. Two paths can still join to one name (``("a", "b")`` and ``("a_b",)``
    both give ``_obj_a_b``), and it does not matter: a capture is read on the
    line that follows it, and a nested object's path always extends its
    parent's, so the pair that could overwrite each other cannot be nested.
    """
    return "_obj" + "".join(f"_{part}" for part in path)


def render_object(fields: list[OutputField], depth: int, var: str) -> str:
    """Assemble a JSON object literal, required fields first.

    Every key renders with a comma in front of it, so the body is captured and
    the first comma stripped off whatever survived. An object therefore needs
    no unconditional key of its own: one whose fields are all optional renders
    as ``{}`` until one of them is answered. Ordering required keys first is
    only about how the document reads — it is no longer what makes it parse.

    The newline after the ``{`` is load-bearing twice over: it separates the
    brace from the ``{%-`` that follows (``{{%`` would lex as a variable), and
    that same ``{%-`` eats it back, leaving the newline the stripped comma
    gives up.
    """
    required = [f for f in fields if f.required]
    optional = [f for f in fields if not f.required]
    body = "".join(f.render(depth) for f in required + optional)
    closing_indent = "  " * (depth - 1)
    return (
        "{\n"
        f"{{%- set {var}_raw %}}{body}{{%- endset %}}"
        f"{{%- set {var} = {var}_raw.lstrip()[1:] -%}}"
        f"{{{{ {var} }}}}\n{closing_indent}}}"
    )


class TemplateBuilder:
    """Accumulates the answer-label table while building the output tree."""

    def __init__(self, config: dict[str, Any]):
        self.computed_fields = computed_fields_from_config(config)
        # answer_uuid -> label, for the template's AL Jinja dict, which
        # translates a stored answer UUID back into its literal label.
        self.answer_labels: dict[str, str] = {}

    def build_scalar_field(self, field: Field, chain: list[str]) -> OutputField:
        """A scalar field — plain value, strict or suggested options with
        their "Other" follow-up, or boolean. Always one line, hence no
        depth."""
        kind = field_kind(field, self.computed_fields)
        own_chain = chain + [q(question_uuid(field.path))]
        own_path = reply_path_expr(own_chain)

        if kind == "options_suggested" and needs_a_synthetic_escape(field):
            for value in field.suggested_values:
                self.answer_labels[answer_uuid(field.path, value)] = value
            other_chain = chain + [
                q(question_uuid(field.path)),
                q(other_answer_uuid(field.path)),
                q(other_followup_uuid(field.path)),
            ]
            other_path = reply_path_expr(other_chain)
            # 'other' is the sentinel that *detects* the "Other" answer: its
            # uuid is deliberately kept out of AL, so the lookup falling back
            # to 'other' is what identifies it. Do not add it to AL. The value
            # finally emitted falls back to '' instead, never to 'other'.
            #
            # `jv` and `js` rather than `sv` and `av`: this is the one branch
            # that renders something a researcher typed by hand, so it is the
            # one that most needs escaping — a single quote in it used to end
            # the JSON string and take the whole document down with it.
            value_expr = (
                f"jv({other_path}) if (av({own_path}, 'other') == 'other' and "
                f"{other_path} in r and r[{other_path}]|reply_str_value) "
                f"else js(av({own_path}, ''))"
            )
        elif kind in ("options_strict", "options_suggested"):
            # A closed vocabulary, or a suggested one naming its own escape:
            # either way every value is an answer of its own, so there is no
            # sentinel to detect and the label table carries the lot.
            for value in field.allowed_values or field.suggested_values:
                self.answer_labels[answer_uuid(field.path, value)] = value
            # Default to '', never to a vocabulary value: 'unknown' is a
            # legitimate answer for ethical_issues_exist, personal_data and
            # sensitive_data, so an unanswered question would be
            # indistinguishable from a deliberate "I don't know".
            #
            # Escaped like any other string: a label is a standard's prose, and
            # a standard is free to spell a value with a quote in it.
            value_expr = f"js(av({own_path}, ''))"
        elif kind == "boolean":
            for value in ("yes", "no"):
                self.answer_labels[answer_uuid(field.path, value)] = value
            # A JSON boolean, not a quoted string: the Yes/No answer maps to a
            # bare true/false literal.
            condition = f"{own_path} in r and r[{own_path}]|reply_str_value"
            return OutputField(
                field.name,
                f"{{{{ 'true' if av({own_path}, 'no') == 'yes' else 'false' }}}}",
                required=field.cardinality == "1",
                condition=condition,
                is_object=True,
            )
        elif kind == "value":
            value_expr = f"jv({own_path})"
        else:
            # Named rather than defaulted, for the reason `generate_km` gives:
            # a kind rendered as a plain value is a document that reads a
            # question the KM asked as something else. "computed" lands here
            # too — reaching it means a caller forgot to fill it from the
            # render context.
            raise ValueError(f"{field.dotted_path}: nothing renders kind {kind!r}")

        condition = f"{own_path} in r and r[{own_path}]|reply_str_value"
        return OutputField(
            field.name,
            value_expr,
            required=field.cardinality == "1",
            condition=condition,
        )

    def build_multi_choice_field(
        self, field: Field, chain: list[str], depth: int
    ) -> OutputField:
        """An ``options_*_multi`` field: a JSON array of every chosen label,
        appending the one manually-entered value from an "other" follow-up
        where the field was given one.

        Which vocabulary the values come from is all this needs of the kind:
        both multi kinds render the same array, and whether a follow-up exists
        is :func:`dsw.common.needs_a_synthetic_escape`'s answer, not the
        kind's."""
        own_path = reply_path_expr(chain + [q(question_uuid(field.path))])

        values = list(field.allowed_values or field.suggested_values)
        for value in values:
            self.answer_labels[answer_uuid(field.path, value)] = value

        item_var = f"{'_'.join(field.path)}_choice"
        preamble = (
            f"{{%- set {item_var}_items = r[{own_path}]|reply_items "
            f"if {own_path} in r else [] %}}\n"
        )

        other_var = None
        if needs_a_synthetic_escape(field):
            other_path = reply_path_expr(chain + [q(other_followup_uuid(field.path))])
            # Held raw, escaped where it is emitted: the same variable decides
            # whether the array has a last comma and whether the key renders at
            # all, and both of those are questions about the value the
            # researcher typed, not about its JSON spelling.
            other_var = f"{item_var}_other"
            preamble += (
                f"{{%- set {other_var} = sv({other_path}) if {other_path} in r and "
                f"r[{other_path}]|reply_str_value else '' %}}\n"
            )

        item_indent = "  " * (depth + 1)
        closing_indent = "  " * depth
        comma_guard = f" or {other_var}" if other_var else ""
        lines = [
            "[",
            f"{{%- for {item_var}_uuid in {item_var}_items %}}",
            (
                f"{item_indent}\"{{{{ js(AL.get({item_var}_uuid, 'unknown')) }}}}\""
                f"{{% if not loop.last{comma_guard} %}},{{% endif %}}"
            ),
            "{%- endfor %}",
        ]
        if other_var:
            lines += [
                f"{{%- if {other_var} %}}",
                f'{item_indent}"{{{{ js({other_var}) }}}}"',
                "{%- endif %}",
            ]
        lines.append(f"{closing_indent}]")

        condition = f"{item_var}_items" + (f" or {other_var}" if other_var else "")
        return OutputField(
            field.name,
            "\n".join(lines),
            required=False,
            condition=condition,
            is_object=True,
            preamble=preamble,
        )

    def build_scalar_list_field(
        self, field: Field, chain: list[str], depth: int
    ) -> OutputField:
        """A ``value_multi`` field: reads, for each list item, the
        item-template ValueQuestion the KM emitted."""
        list_path = reply_path_expr(chain + [q(question_uuid(field.path))])
        item_var = f"{'_'.join(field.path)}_item"
        item_value_path = reply_path_expr(
            [list_path, f"{item_var}_uuid", q(list_item_value_uuid(field.path))]
        )

        item_indent = "  " * (depth + 1)
        closing_indent = "  " * depth
        preamble = (
            f"{{%- set {item_var}_items = r[{list_path}]|reply_items "
            f"if {list_path} in r else [] %}}\n"
        )
        value = (
            f"[\n"
            f"{{%- for {item_var}_uuid in {item_var}_items %}}\n"
            f'{item_indent}"{{{{ jv({item_value_path}) }}}}"'
            f"{{% if not loop.last %}},{{% endif %}}\n"
            f"{{%- endfor %}}\n"
            f"{closing_indent}]"
        )
        return OutputField(
            field.name,
            value,
            required=False,
            condition=f"{item_var}_items",
            is_object=True,
            preamble=preamble,
        )

    def build_gated_object_field(
        self, field: Field, chain: list[str], depth: int
    ) -> OutputField:
        """A ``0..1`` gated object: the JSON key appears only when the gate
        was answered "Yes", mirroring the KM's gate."""
        gate_path = reply_path_expr(chain + [q(gate_uuid(field.path))])
        yes_chain = chain + [q(gate_uuid(field.path)), q(gate_yes_uuid(field.path))]

        sub_fields = [
            self.build_any_field(child, yes_chain, depth + 1)
            for child in field.children
        ]
        condition = (
            f"{gate_path} in r and r[{gate_path}]|reply_str_value == "
            f"{q(gate_yes_uuid(field.path))}"
        )
        return OutputField(
            field.name,
            render_object(sub_fields, depth + 1, object_var(field.path)),
            required=False,
            condition=condition,
            is_object=True,
        )

    def build_list_field(
        self, field: Field, chain: list[str], depth: int
    ) -> OutputField:
        """A list of objects: a Jinja ``{% for %}`` over the list's items,
        rebuilding each item's reply path from its item UUID."""
        list_path = reply_path_expr(chain + [q(question_uuid(field.path))])
        item_var = f"{'_'.join(field.path)}_item"

        sub_fields = [
            self.build_any_field(child, [f"{item_var}_path"], depth + 2)
            for child in field.children
        ]
        item_obj = render_object(sub_fields, depth + 2, object_var(field.path))
        item_indent = "  " * (depth + 1)
        closing_indent = "  " * depth

        preamble = (
            f"{{%- set {item_var}_items = r[{list_path}]|reply_items "
            f"if {list_path} in r else [] %}}\n"
        )
        value = (
            f"[\n"
            f"{{%- for {item_var}_uuid in {item_var}_items %}}\n"
            f"{{%- set {item_var}_path = [{list_path}, {item_var}_uuid]|reply_path %}}\n"
            f"{item_indent}{item_obj}{{% if not loop.last %}},{{% endif %}}\n"
            f"{{%- endfor %}}\n"
            f"{closing_indent}]"
        )
        return OutputField(
            field.name,
            value,
            required=False,
            condition=f"{item_var}_items",
            is_object=True,
            preamble=preamble,
        )

    def build_any_field(
        self, field: Field, chain: list[str], depth: int
    ) -> OutputField:
        kind = field_kind(field, self.computed_fields)
        if kind == "object_inline":
            sub_fields = [
                self.build_any_field(child, chain, depth + 1)
                for child in field.children
            ]
            return OutputField(
                field.name,
                render_object(sub_fields, depth + 1, object_var(field.path)),
                required=True,
                is_object=True,
            )
        if kind == "object_gated":
            return self.build_gated_object_field(field, chain, depth)
        if kind == "list":
            return self.build_list_field(field, chain, depth)
        if kind in ("options_strict_multi", "options_suggested_multi"):
            return self.build_multi_choice_field(field, chain, depth)
        if kind == "value_multi":
            return self.build_scalar_list_field(field, chain, depth)
        return self.build_scalar_field(field, chain)


# The DMP's current URL in DSW, resolved entirely from the render context:
# ctx.config.clientUrl is the DSW instance's client base URL, ctx.project.uuid
# the questionnaire — no config needed. A stable placeholder the submission
# webhook rewrites to the dmp-registry location when it commits the DMP.
DSW_DMP_ID_URL = "{{ ctx.config.clientUrl }}/projects/{{ ctx.project.uuid }}"


def _dsw_dmp_id_field(depth: int) -> OutputField:
    child_indent = "  " * (depth + 1)
    closing_indent = "  " * depth
    value = (
        "{\n"
        f'{child_indent}"identifier": "{DSW_DMP_ID_URL}",\n'
        f'{child_indent}"type": "url"\n'
        f"{closing_indent}}}"
    )
    return OutputField("dmp_id", value, required=True, is_object=True)


def build_template_bundle(
    project: Project, created_at: str | None = None
) -> dict[str, Any]:
    """The full DSW ``DocumentTemplate`` bundle for one project, ready for the
    ``document-templates/bundle`` endpoint.

    ``created_at`` is injectable for the same reason as the KM's: everything
    else is derived from the project, so two runs give the same bytes.
    """
    created_at = created_at or utc_timestamp()
    config, model = project.config, project.model
    pid = package_id(config)
    builder = TemplateBuilder(config)

    general, chapters = top_level_split(model)

    root_fields: list[OutputField] = []
    general_chain = [q(chapter_uuid("general"))]
    for field in general:
        if field.name in builder.computed_fields:
            expr = COMPUTED_FIELD_EXPR.get(field.name)
            if expr is not None:
                root_fields.append(OutputField(field.name, expr, required=True))
            continue
        # Through the same door as a chapter field, not straight to the scalar
        # builder: a top-level field is a scalar by definition of the split,
        # but a scalar can still be a list through its cardinality, and this
        # one used to render as a single value while the KM asked for a list.
        root_fields.append(builder.build_any_field(field, general_chain, depth=2))

    for field in chapters:
        if field.name in builder.computed_fields:
            # A computed field carries no reply to render; only dmp_id has an
            # expression to emit (see DSW_DMP_ID_URL). Any other one is simply
            # absent from the document.
            if field.name == "dmp_id":
                root_fields.append(_dsw_dmp_id_field(depth=2))
            continue
        root_fields.append(
            builder.build_any_field(field, [q(chapter_uuid(field.name))], depth=2)
        )

    dmp_object = render_object(root_fields, 2, object_var(()))

    al_entries = ",\n".join(
        f"  {q(uuid_)}: {q(label)}"
        for uuid_, label in sorted(builder.answer_labels.items())
    )
    al_dict = "{\n" + al_entries + "\n}"

    template_body = (
        "{% autoescape false %}\n"
        "{%- set r = ctx.project.replies -%}\n\n"
        f"{{%- set AL = {al_dict} -%}}\n\n"
        "{#- js() is what makes a string safe to sit between two quotes; every\n"
        "    macro and every expression below that renders text goes through it,\n"
        "    because the document is assembled as literal JSON and there is\n"
        "    nothing else standing between a reply and the file. -#}\n"
        f"{{%- macro js(text) -%}}{{{{ {_json_escape_chain('text')} }}}}{{%- endmacro -%}}\n"
        "{%- macro sv(path) -%}{{ r[path]|reply_str_value if path in r else '' }}{%- endmacro -%}\n"
        "{%- macro av(path, default='') -%}{{ AL.get(r[path]|reply_str_value, default) if path in r else default }}{%- endmacro -%}\n"
        "{%- macro jv(path) -%}{{ js(r[path]|reply_str_value) if path in r else '' }}{%- endmacro -%}\n\n"
        "{#- All chapter/question UUIDs below come from dsw/uuids.py, the exact\n"
        "    same functions generate_km.py uses, so they always match the\n"
        "    published KM by construction, never a hand-copied table. -#}\n\n"
        "{\n"
        '  "dmp": ' + dmp_object + "\n"
        "}\n"
        "{% endautoescape %}\n"
    )

    template_filename = f"{config['id'].replace('-', '_')}.json.j2"

    def build_readme() -> str:
        standards = [standard_label(s) for s in model.standards]
        base, extensions = standards[0], standards[1:]
        coverage = (
            base if not extensions else f"{base}, extended with {', '.join(extensions)}"
        )
        lines = readme_head(config, "Document Template") + [
            "## Output",
            "",
            f"Structured around the `dmp` root object, covering {coverage}.",
            "",
            "| Format | Status | Notes |",
            "|---|---|---|",
        ]
        for fmt in FORMATS:
            status = "Available" if fmt["available"] else "Planned"
            lines.append(f"| {fmt['name']} | {status} | {fmt['notes']} |")
        lines.append("")
        if COMPUTED_FIELD_EXPR:
            lines += [
                (
                    "Auto-filled from the DSW project itself rather than from "
                    "the researcher's replies:"
                ),
                "",
            ]
            for field_name, expr in sorted(COMPUTED_FIELD_EXPR.items()):
                lines.append(f"- `dmp.{field_name}`, from `{expr}`")
            lines.append(
                "- `dmp.dmp_id`, the DMP's current URL in DSW "
                "(`ctx.config.clientUrl` + `/projects/<uuid>`); the submission "
                "webhook rewrites it to the dmp-registry location on commit"
            )
            lines.append("")
        lines += readme_tail(
            config,
            [
                f"Knowledge Model: `{pid}`",
                (f"DS Wizard template metamodel version: {TEMPLATE_METAMODEL_VERSION}"),
                rules_provenance_line(model),
            ],
        )
        return "\n".join(lines)

    return {
        "allowedPackages": [
            {
                "kmId": config["id"],
                "maxVersion": None,
                "minVersion": None,
                "orgId": config["organizationId"],
            }
        ],
        "assets": [],
        "createdAt": created_at,
        # Plain text on purpose: DSW renders a package's description as plain
        # text and never as Markdown.
        "description": strip_markdown(config["description"]),
        "formats": [
            {
                "icon": "fas fa-file-code",
                "name": f"maDMP {fmt['name']} ({config['id']})",
                "steps": [
                    {
                        "name": "jinja",
                        "options": {
                            "content-type": fmt["content_type"],
                            "extension": fmt["extension"],
                            "template": template_filename,
                        },
                    }
                ],
                "uuid": format_uuid(fmt["name"]),
            }
            for fmt in FORMATS
            if fmt["available"]
        ],
        "id": pid,
        "license": config["license"],
        "metamodelVersion": TEMPLATE_METAMODEL_VERSION,
        "name": config["name"],
        "organizationId": config["organizationId"],
        "readme": build_readme(),
        "templateId": config["id"],
        "version": config["version"],
        "files": [
            {
                "fileName": template_filename,
                # DSW keys a file's content by this uuid, so it must not be
                # reused across published versions — stale content would be
                # served for the new one. It must not be random either: two
                # runs of one project have to give the same bundle. Deriving
                # it from the package id satisfies both, the id carrying the
                # project version that a publish requires bumping.
                "uuid": u("template", "file", pid, template_filename),
                "content": template_body,
            }
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="path to a project config")
    parser.add_argument(
        "--out",
        help="output bundle path (defaults to build/template/<id>_template.json)",
    )
    args = parser.parse_args(argv)

    project = assemble_project(args.config)
    bundle = build_template_bundle(project)

    out = Path(args.out) if args.out else template_path(project.config["id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    print(f"Generated template bundle -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
