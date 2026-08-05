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
- The output is assembled as literal JSON text: required keys joined by
  literal commas, each optional key wrapped in its own ``{%- if ... %}``
  block. **Every object therefore needs at least one unconditional key as a
  comma anchor** — which is why a required field is emitted even when nothing
  answered it. See ``doc.md`` ("Le template de document").
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dsw.common import (
    BUILD_DIR,
    computed_fields_from_config,
    field_kind,
    package_id,
    readme_head,
    readme_tail,
    rules_provenance_line,
    standard_label,
    strip_markdown,
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

OUTPUT_DIR = BUILD_DIR / "template"

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
        "name": "JSON",
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


def q(uuid_str: str) -> str:
    """Quote a UUID, or a variable name, as a Jinja string literal."""
    return f"'{uuid_str}'"


class OutputField:
    """One emitted JSON ``"key": value`` pair of the output template.

    ``required`` keys are always emitted, comma-joined; optional keys are each
    wrapped in their own ``{%- if condition %}`` block. ``is_object`` marks
    ``value_expr`` as raw JSON/Jinja text rather than a scalar to quote, and
    ``preamble`` holds the ``{% set %}`` statements that must run before
    ``condition`` is evaluated.
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
        """Render as an indented fragment. For object and array values the
        caller must have built ``value_expr`` with ``depth + 1`` for its
        children — see :func:`render_object`."""
        indent = "  " * depth
        v = self.value_expr if self.is_object else f'"{{{{ {self.value_expr} }}}}"'
        line = f'{indent}"{self.key}": {v}'
        if self.required:
            return self.preamble + line
        return f"{self.preamble}{{%- if {self.condition} %}},\n{line}\n{{%- endif %}}"


def render_object(fields: list[OutputField], depth: int) -> str:
    """Assemble a JSON object literal: the required fields comma-joined first,
    then each optional field guarding itself with its own Jinja block."""
    required = [f for f in fields if f.required]
    optional = [f for f in fields if not f.required]
    body = ",\n".join(f.render(depth) for f in required)
    for f in optional:
        body += "\n" + f.render(depth)
    closing_indent = "  " * (depth - 1)
    return "{\n" + body + "\n" + closing_indent + "}"


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

        if kind == "options_suggested":
            for value in field.suggested_values:
                if value.lower() != "other":
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
            value_expr = (
                f"sv({other_path}) if (av({own_path}, 'other') == 'other' and "
                f"{other_path} in r and r[{other_path}]|reply_str_value) "
                f"else av({own_path}, '')"
            )
        elif kind == "options_strict":
            for value in field.allowed_values:
                self.answer_labels[answer_uuid(field.path, value)] = value
            # Default to '', never to a vocabulary value: 'unknown' is a
            # legitimate answer for ethical_issues_exist, personal_data and
            # sensitive_data, so an unanswered question would be
            # indistinguishable from a deliberate "I don't know".
            value_expr = f"av({own_path}, '')"
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
        else:
            value_expr = f"jv({own_path})"

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
        the suggested case appending the one manually-entered value from its
        "other" follow-up when filled."""
        kind = field_kind(field, self.computed_fields)
        own_path = reply_path_expr(chain + [q(question_uuid(field.path))])

        strict = kind == "options_strict_multi"
        values = (
            list(field.allowed_values)
            if strict
            else [v for v in field.suggested_values if v.lower() != "other"]
        )
        for value in values:
            self.answer_labels[answer_uuid(field.path, value)] = value

        item_var = f"{'_'.join(field.path)}_choice"
        preamble = (
            f"{{%- set {item_var}_items = r[{own_path}]|reply_items "
            f"if {own_path} in r else [] %}}\n"
        )

        other_var = None
        if not strict:
            other_path = reply_path_expr(chain + [q(other_followup_uuid(field.path))])
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
                f"{item_indent}\"{{{{ AL.get({item_var}_uuid, 'unknown') }}}}\""
                f"{{% if not loop.last{comma_guard} %}},{{% endif %}}"
            ),
            "{%- endfor %}",
        ]
        if other_var:
            lines += [
                f"{{%- if {other_var} %}}",
                f'{item_indent}"{{{{ {other_var} }}}}"',
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
            render_object(sub_fields, depth + 1),
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
        item_obj = render_object(sub_fields, depth + 2)
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
                render_object(sub_fields, depth + 1),
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
        root_fields.append(builder.build_scalar_field(field, general_chain))

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

    dmp_object = render_object(root_fields, depth=2)

    al_entries = ",\n".join(
        f"  {q(uuid_)}: {q(label)}"
        for uuid_, label in sorted(builder.answer_labels.items())
    )
    al_dict = "{\n" + al_entries + "\n}"

    template_body = (
        "{% autoescape false %}\n"
        "{%- set r = ctx.project.replies -%}\n\n"
        f"{{%- set AL = {al_dict} -%}}\n\n"
        "{%- macro sv(path) -%}{{ r[path]|reply_str_value if path in r else '' }}{%- endmacro -%}\n"
        "{%- macro av(path, default='') -%}{{ AL.get(r[path]|reply_str_value, default) if path in r else default }}{%- endmacro -%}\n"
        "{%- macro jv(path) -%}{{ r[path]|reply_str_value|replace('\\\\', '\\\\\\\\')|replace('\"', '\\\\\"')|replace('\\n', '\\\\n')|replace('\\r', '') if path in r else '' }}{%- endmacro -%}\n\n"
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
                f"- Knowledge Model: `{pid}`",
                (
                    f"- DS Wizard template metamodel version: "
                    f"{TEMPLATE_METAMODEL_VERSION}"
                ),
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
                "uuid": u("template", "format", fmt["name"]),
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

    out = (
        Path(args.out)
        if args.out
        else OUTPUT_DIR / f"{project.config['id']}_template.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    print(f"Generated template bundle -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
