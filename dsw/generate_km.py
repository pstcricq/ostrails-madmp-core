"""Knowledge Model generator: a merged rules model -> a DSW event bundle.

Walks the model and emits a full DS Wizard Knowledge Model (``.km``) event
bundle — chapters, questions, answers and gates — ready to publish through the
``knowledge-model-packages/bundle`` endpoint.

Which DSW entity a field becomes is :func:`dsw.common.field_kind`'s call and
never this module's; :func:`KmBuilder.process_field` only dispatches on the
answer. What each entity's UUID is, is :mod:`dsw.uuids`' call.

Emission order matters: DSW infers the order of sibling entities from the
order of the events sharing a ``parentUuid``, so the order questions are
emitted in is the order a researcher reads them.

The full rules-to-entity mapping, and why it is that way, is in ``doc.md``
("Le questionnaire").
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dsw.common import (
    BUILD_DIR,
    computed_fields_from_config,
    field_kind,
    needs_a_synthetic_escape,
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
    gate_no_uuid,
    gate_uuid,
    gate_yes_uuid,
    list_item_value_uuid,
    other_answer_uuid,
    other_followup_uuid,
    question_uuid,
    u,
)
from project import Field, Model, Project, assemble_project

OUTPUT_DIR = BUILD_DIR / "km"

# The DSW metamodel schema version this bundle targets. Tied to the DSW
# instance and not to the project (20 for DSW v4.31): see
# https://github.com/ds-wizard/dsw-schemas/tree/main/schemas/km-package
METAMODEL_VERSION = 20

# A scalar field type, as the matching DSW ValueQuestion value type. Several
# rules types share one DSW type: DSW validates the shape it knows, and the
# narrower constraint stays the QC's to check.
VALUE_TYPE_MAP: dict[str, str] = {
    "string": "StringQuestionValueType",
    "number": "NumberQuestionValueType",
    "date": "DateQuestionValueType",
    "email": "EmailQuestionValueType",
    "url": "UrlQuestionValueType",
    "language": "StringQuestionValueType",
    "country_code": "StringQuestionValueType",
    "currency": "StringQuestionValueType",
    "datetime": "DateTimeQuestionValueType",
}

ORIGIN_COLORS = ["#9b59b6", "#e67e22", "#16a085", "#2c3e50", "#f39c12", "#7f8c8d"]

GENERAL_CHAPTER_TITLE = "DMP General Information"
GENERAL_CHAPTER_DESC = "General information about the Data Management Plan."


def humanize(key: str) -> str:
    """``"data_type"`` -> ``"Data Type"``."""
    return " ".join(w.capitalize() for w in key.split("_"))


def title_for(field: Field) -> str:
    """A question or chapter title, from the field's own key. The rules
    declare a description, never a title: a title that had to be written
    would be a title that could disagree with the field it names."""
    return humanize(field.name)


def path_annotation(path: tuple[str, ...]) -> list[dict[str, str]]:
    """The DSW annotation tracing an entity back to its rules field, so that a
    later consumer can map an answer to the path it fills."""
    return [{"key": "rules_path", "value": ".".join(path)}]


class KmBuilder:
    """Accumulates the DSW events of one KM generation run."""

    def __init__(self, config: dict[str, Any], model: Model, created_at: str):
        self.config = config
        self.model = model
        self.created_at = created_at
        self.computed_fields = computed_fields_from_config(config)
        self.events: list[dict[str, Any]] = []
        self.chapters_toc: list[tuple[str, str]] = []
        self.km_uuid = u("root")
        self.phase_uuid = u("phase", "required")
        self.tag_required = u("tag", "required")
        self.tag_optional = u("tag", "optional")
        self.tag_cv = u("tag", "cv")
        self.tag_origin = {
            origin: u("tag", "origin", origin) for origin in model.standards
        }

    def emit(self, entity_uuid: str, parent_uuid: str, content: dict[str, Any]) -> None:
        self.events.append(
            {
                "uuid": u(entity_uuid, "event"),
                "entityUuid": entity_uuid,
                "parentUuid": parent_uuid,
                "createdAt": self.created_at,
                "content": content,
            }
        )

    # Root, phase, tags

    def emit_root(self) -> None:
        self.emit(
            self.km_uuid,
            "00000000-0000-0000-0000-000000000000",
            {"eventType": "AddKnowledgeModelEvent", "annotations": []},
        )
        self.emit(
            self.phase_uuid,
            self.km_uuid,
            {
                "eventType": "AddPhaseEvent",
                "annotations": [],
                "title": "Required fields",
                "description": (
                    "Fields the merged rules mark as required (cardinality 1 "
                    "or 1..n). Which standard imposes it is shown by the "
                    "question's own standard tag."
                ),
            },
        )
        for tag_uuid, name, color, description in [
            (
                self.tag_required,
                "REQUIRED",
                "#e74c3c",
                (
                    "Required field. The standard tag beside it says which "
                    "standard requires it."
                ),
            ),
            (self.tag_optional, "OPTIONAL", "#95a5a6", "Optional field."),
            (
                self.tag_cv,
                "CONTROLLED VOCABULARY",
                "#3498db",
                "Value taken from a controlled vocabulary.",
            ),
        ]:
            self.emit(
                tag_uuid,
                self.km_uuid,
                {
                    "eventType": "AddTagEvent",
                    "annotations": [],
                    "name": name,
                    "color": color,
                    "description": description,
                },
            )
        # One tag per standard, derived from each file's own `standard`
        # declaration, so that adding a rules file never means wiring its tag
        # by hand. Identity from the code name, display from `standard_label`:
        # the uuid stays put whatever a reader is shown.
        for i, origin in enumerate(self.model.standards):
            label = standard_label(origin)
            self.emit(
                self.tag_origin[origin],
                self.km_uuid,
                {
                    "eventType": "AddTagEvent",
                    "annotations": [],
                    "name": label,
                    "color": ORIGIN_COLORS[i % len(ORIGIN_COLORS)],
                    "description": f"Field defined by the {label} standard.",
                },
            )

    def tags_for(self, field: Field) -> list[str]:
        tags = [self.tag_required if field.is_required else self.tag_optional]
        origin_tag = self.tag_origin.get(field.origin)
        if origin_tag is not None:
            tags.append(origin_tag)
        if field.allowed_values is not None or field.suggested_values is not None:
            tags.append(self.tag_cv)
        return tags

    def required_phase_for(self, field: Field) -> str | None:
        return self.phase_uuid if field.is_required else None

    # Question emitters

    def emit_value_question(self, field: Field, parent_uuid: str) -> None:
        self.emit(
            question_uuid(field.path),
            parent_uuid,
            {
                "eventType": "AddQuestionEvent",
                "questionType": "ValueQuestion",
                "annotations": path_annotation(field.path),
                "title": title_for(field),
                "text": field.description,
                "requiredPhaseUuid": self.required_phase_for(field),
                "tagUuids": self.tags_for(field),
                "valueType": VALUE_TYPE_MAP[field.type],
                "validations": [],
            },
        )

    def emit_options_question(
        self, field: Field, parent_uuid: str, values: list[str], escape: bool
    ) -> None:
        """An ``OptionsQuestion`` with one answer per value, plus — when
        ``escape`` — an extra "Other" answer opening a free-text follow-up.

        ``escape`` is :func:`dsw.common.needs_a_synthetic_escape`'s call, never
        this method's: a vocabulary naming an escape of its own is emitted with
        it and given nothing else, which is also what keeps the synthetic
        answer from claiming a UUID the declared one already has."""
        q_uuid = question_uuid(field.path)
        self.emit(
            q_uuid,
            parent_uuid,
            {
                "eventType": "AddQuestionEvent",
                "questionType": "OptionsQuestion",
                "annotations": path_annotation(field.path),
                "title": title_for(field),
                "text": field.description,
                "requiredPhaseUuid": self.required_phase_for(field),
                "tagUuids": self.tags_for(field),
                "answerUuids": [],
            },
        )
        for value in values:
            self.emit(
                answer_uuid(field.path, value),
                q_uuid,
                {
                    "eventType": "AddAnswerEvent",
                    "annotations": [],
                    "label": value,
                    "advice": None,
                    "metricMeasures": [],
                },
            )
        if escape:
            other_uuid = other_answer_uuid(field.path)
            self.emit(
                other_uuid,
                q_uuid,
                {
                    "eventType": "AddAnswerEvent",
                    "annotations": [],
                    "label": "Other",
                    "advice": None,
                    "metricMeasures": [],
                },
            )
            self.emit(
                other_followup_uuid(field.path),
                other_uuid,
                {
                    "eventType": "AddQuestionEvent",
                    "questionType": "ValueQuestion",
                    "annotations": path_annotation(field.path + ("other",)),
                    "title": f"{title_for(field)} (specify)",
                    "text": (
                        "Suggested values are not exhaustive: enter the value manually."
                    ),
                    "requiredPhaseUuid": self.required_phase_for(field),
                    "tagUuids": [
                        self.tag_required if field.is_required else self.tag_optional
                    ],
                    "valueType": "StringQuestionValueType",
                    "validations": [],
                },
            )

    def emit_multi_choice_question(
        self, field: Field, parent_uuid: str, values: list[str]
    ) -> None:
        q_uuid = question_uuid(field.path)
        self.emit(
            q_uuid,
            parent_uuid,
            {
                "eventType": "AddQuestionEvent",
                "questionType": "MultiChoiceQuestion",
                "annotations": path_annotation(field.path),
                "title": title_for(field),
                "text": field.description,
                "requiredPhaseUuid": self.required_phase_for(field),
                "tagUuids": self.tags_for(field),
            },
        )
        for value in values:
            self.emit(
                answer_uuid(field.path, value),
                q_uuid,
                {"eventType": "AddChoiceEvent", "annotations": [], "label": value},
            )

    def emit_other_followup(self, field: Field, parent_uuid: str) -> None:
        """A free-text follow-up beside a suggested MultiChoiceQuestion: a
        multi-choice has no "Other" choice to hang a question off, so the
        manual entry sits next to it instead of under it."""
        self.emit(
            other_followup_uuid(field.path),
            parent_uuid,
            {
                "eventType": "AddQuestionEvent",
                "questionType": "ValueQuestion",
                "annotations": path_annotation(field.path + ("other",)),
                "title": f"{title_for(field)} (specify)",
                "text": (
                    "Suggested values are not exhaustive: enter an additional "
                    "value manually."
                ),
                "requiredPhaseUuid": None,
                "tagUuids": [self.tag_optional],
                "valueType": "StringQuestionValueType",
                "validations": [],
            },
        )

    def emit_multi_value_question(self, field: Field, parent_uuid: str) -> None:
        """A ListQuestion whose single item template is a ValueQuestion — a
        scalar repeated through its cardinality, DSW having no other way to
        ask for several of one value."""
        q_uuid = question_uuid(field.path)
        self.emit(
            q_uuid,
            parent_uuid,
            {
                "eventType": "AddQuestionEvent",
                "questionType": "ListQuestion",
                "annotations": path_annotation(field.path),
                "title": title_for(field),
                "text": field.description,
                "requiredPhaseUuid": self.required_phase_for(field),
                "tagUuids": self.tags_for(field),
                "itemTemplateQuestionUuids": [],
            },
        )
        self.emit(
            list_item_value_uuid(field.path),
            q_uuid,
            {
                "eventType": "AddQuestionEvent",
                "questionType": "ValueQuestion",
                "annotations": [],
                "title": title_for(field),
                "text": field.description,
                "requiredPhaseUuid": None,
                "tagUuids": [],
                "valueType": VALUE_TYPE_MAP[field.type],
                "validations": [],
            },
        )

    def emit_gate(
        self, field: Field, parent_uuid: str, on_yes: Callable[[str], None]
    ) -> None:
        """A Yes/No gate question for a ``0..1`` object; ``on_yes`` emits the
        field's children under the "Yes" answer, so an optional block asks
        nothing until it is opted into."""
        gate_q_uuid = gate_uuid(field.path)
        self.emit(
            gate_q_uuid,
            parent_uuid,
            {
                "eventType": "AddQuestionEvent",
                "questionType": "OptionsQuestion",
                "annotations": path_annotation(field.path),
                "title": f"Specify {title_for(field).lower()}?",
                "text": "**Optional.** Answer Yes to provide these details.",
                "requiredPhaseUuid": None,
                "tagUuids": [self.tag_optional],
                "answerUuids": [],
            },
        )
        yes_uuid = gate_yes_uuid(field.path)
        for a_uuid, label in [(yes_uuid, "Yes"), (gate_no_uuid(field.path), "No")]:
            self.emit(
                a_uuid,
                gate_q_uuid,
                {
                    "eventType": "AddAnswerEvent",
                    "annotations": [],
                    "label": label,
                    "advice": None,
                    "metricMeasures": [],
                },
            )
        on_yes(yes_uuid)

    def process_field(self, field: Field, parent_uuid: str) -> None:
        """Emit the question(s) for one field and its descendants, dispatching
        on the kind `common` decided."""
        kind = field_kind(field, self.computed_fields)
        if kind == "computed":
            return
        if kind == "list":
            q_uuid = question_uuid(field.path)
            self.emit(
                q_uuid,
                parent_uuid,
                {
                    "eventType": "AddQuestionEvent",
                    "questionType": "ListQuestion",
                    "annotations": path_annotation(field.path),
                    "title": title_for(field),
                    "text": field.description,
                    "requiredPhaseUuid": self.required_phase_for(field),
                    "tagUuids": self.tags_for(field),
                    "itemTemplateQuestionUuids": [],
                },
            )
            for child in field.children:
                self.process_field(child, q_uuid)
        elif kind == "object_gated":
            self.emit_gate(
                field,
                parent_uuid,
                lambda yes_uuid: [
                    self.process_field(child, yes_uuid) for child in field.children
                ],
            )
        elif kind == "object_inline":
            for child in field.children:
                self.process_field(child, parent_uuid)
        elif kind == "options_strict":
            self.emit_options_question(
                field, parent_uuid, list(field.allowed_values), escape=False
            )
        elif kind == "options_suggested":
            self.emit_options_question(
                field,
                parent_uuid,
                list(field.suggested_values),
                escape=needs_a_synthetic_escape(field),
            )
        elif kind == "options_strict_multi":
            self.emit_multi_choice_question(
                field, parent_uuid, list(field.allowed_values)
            )
        elif kind == "options_suggested_multi":
            self.emit_multi_choice_question(
                field, parent_uuid, list(field.suggested_values)
            )
            if needs_a_synthetic_escape(field):
                self.emit_other_followup(field, parent_uuid)
        elif kind == "value_multi":
            self.emit_multi_value_question(field, parent_uuid)
        elif kind == "boolean":
            self.emit_options_question(field, parent_uuid, ["yes", "no"], escape=False)
        elif kind == "value":
            self.emit_value_question(field, parent_uuid)
        else:
            # Named rather than defaulted: a kind this generator does not know
            # emitted as a plain value question is a KM that looks fine and a
            # template that reads something else.
            raise ValueError(f"{field.dotted_path}: no DSW entity for kind {kind!r}")

    def emit_chapters(self, general: list[Field], chapters: list[Field]) -> None:
        general_uuid = chapter_uuid("general")
        self.chapters_toc.append((GENERAL_CHAPTER_TITLE, GENERAL_CHAPTER_DESC))
        self.emit(
            general_uuid,
            self.km_uuid,
            {
                "eventType": "AddChapterEvent",
                "annotations": [],
                "title": f"1. {GENERAL_CHAPTER_TITLE}",
                "text": GENERAL_CHAPTER_DESC,
            },
        )
        for field in general:
            self.process_field(field, general_uuid)

        # A computed chapter field gets no chapter at all, rather than an
        # empty one.
        chapters = [
            f for f in chapters if field_kind(f, self.computed_fields) != "computed"
        ]
        for idx, field in enumerate(chapters, start=2):
            chapter_title = humanize(field.name)
            description = field.chapter_description or (
                f"Auto-generated chapter for `dmp.{field.name}`."
            )
            self.emit(
                chapter_uuid(field.name),
                self.km_uuid,
                {
                    "eventType": "AddChapterEvent",
                    "annotations": path_annotation((field.name,)),
                    "title": f"{idx}. {chapter_title}",
                    "text": description,
                },
            )
            self.chapters_toc.append((chapter_title, description))
            self.process_field(field, chapter_uuid(field.name))

    def build_readme(self) -> str:
        lines = readme_head(self.config, "Knowledge model") + [
            "## Structure",
            "",
            (
                f"The KM is organised into {len(self.chapters_toc)} chapters "
                f"that directly mirror the rules structure:"
            ),
            "",
            "| # | Chapter | Description |",
            "|---|---------|--------------|",
        ]
        for idx, (title, description) in enumerate(self.chapters_toc, start=1):
            lines.append(f"| {idx} | {title} | {description} |")
        lines += [""] + readme_tail(
            self.config,
            [
                f"Requires DS Wizard with metamodel version {METAMODEL_VERSION}.",
                rules_provenance_line(self.model),
            ],
        )
        return "\n".join(lines)


def build_km_bundle(project: Project, created_at: str | None = None) -> dict[str, Any]:
    """The full DSW ``KnowledgeModelPackageBundle`` payload for one project,
    ready for the ``knowledge-model-packages/bundle`` endpoint.

    ``created_at`` is injectable so that two runs of the same project produce
    the same bytes: everything else in the bundle is derived from the project,
    and the timestamp is the only thing that would otherwise move.
    """
    created_at = created_at or utc_timestamp()
    config = project.config
    pid = package_id(config)
    builder = KmBuilder(config, project.model, created_at)
    builder.emit_root()

    general, chapters = top_level_split(project.model)
    builder.emit_chapters(general, chapters)

    return {
        "id": pid,
        "kmId": config["id"],
        "metamodelVersion": METAMODEL_VERSION,
        "name": config["name"],
        "organizationId": config["organizationId"],
        "version": config["version"],
        "packages": [
            {
                "createdAt": created_at,
                # Plain text on purpose: DSW renders a package's description
                # as plain text and never as Markdown.
                "description": strip_markdown(config["description"]),
                "events": builder.events,
                "forkOfPackageId": None,
                "id": pid,
                "kmId": config["id"],
                "license": config["license"],
                "mergeCheckpointPackageId": None,
                "metamodelVersion": METAMODEL_VERSION,
                "name": config["name"],
                "nonEditable": False,
                "organizationId": config["organizationId"],
                "phase": "ReleasedKnowledgeModelPackagePhase",
                "previousPackageId": None,
                "readme": builder.build_readme(),
                "version": config["version"],
            }
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="path to a project config")
    parser.add_argument(
        "--out", help="output .km path (defaults to build/km/<id>_km.km)"
    )
    args = parser.parse_args(argv)

    project = assemble_project(args.config)
    bundle = build_km_bundle(project)

    out = Path(args.out) if args.out else OUTPUT_DIR / f"{project.config['id']}_km.km"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    print(f"Generated {len(bundle['packages'][0]['events'])} events -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
