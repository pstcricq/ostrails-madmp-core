"""Build every project's KM and Document Template under ``build/``.

Two things at once, and both are the point.

A verdict. This is the only place every config goes through the generators, so
it is what says a repository can generate every one of its projects and not
just the one the tests cover deeply. What it checks is what the data decides
rather than what the code decides: that the KM emits no entity twice, and that
the document template is Jinja at all. Both are questions only a project's own
vocabularies can answer, and both would otherwise be answered by DSW, the
first by dropping a question and the second at render time.

The artifacts. What it writes is what a reviewer reads to see what a rules
change did to the questionnaire, and what a publish ships. They are stamped
with the real time, a frozen timestamp being a false creation date carried
into every published package.

Generation reads the config and the rules, and touches neither DSW nor the
registry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jinja2

from dsw.common import BUILD_DIR, km_path, template_path, utc_timestamp
from dsw.generate_km import build_km_bundle
from dsw.generate_template import build_template_bundle
from project import assemble_project
from utils.errors import ProblemsError

PROJECTS = Path(__file__).parent.parent / "configs" / "projects"

# One stamp for the whole run, so that a project's KM and its template carry
# the same creation time however long the run takes.
STAMP = utc_timestamp()


def _duplicate_entities(km: dict) -> list[str]:
    """Entities the KM emits twice, DSW would apply the second event on top of
    the first and one of the two questions would simply not be there.

    Data-dependent, which is why it is checked per config rather than once in
    the tests: `uuids.other_answer_uuid(path)` is by construction
    `answer_uuid(path, "other")`, so a standard whose vocabulary lists the word
    literally collides with the synthetic "Other".
    """
    seen, twice = set(), []
    for event in km["packages"][0]["events"]:
        if event["entityUuid"] in seen:
            twice.append(event["entityUuid"])
        seen.add(event["entityUuid"])
    return twice


def _jinja_error(template: dict) -> str | None:
    """Why the document template's body is not Jinja, if it is not.

    The generator writes Jinja and never runs it, so nothing between here and
    DSW would notice a syntax error, DSW finding out at render time. The unit
    tests parse one project's body, what they cannot parse is a body built
    from vocabularies they have never seen.

    Data-dependent for the same reason the duplicate check is, and for a
    sharper one: a vocabulary label is not only data the template reads, it is
    source the generator writes, the answer-label table holding each one as a
    Jinja literal. `Institut d'Optique` closes that literal early and leaves a
    body that is not Jinja at all.
    """
    try:
        jinja2.Environment().parse(template["files"][0]["content"])
    except jinja2.TemplateSyntaxError as err:
        return f"line {err.lineno}: {err.message}"
    return None


def _write(path: Path, bundle: dict) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    return path.stat().st_size


def main() -> int:
    paths = sorted(PROJECTS.glob("*.yaml"))
    if not paths:
        print(f"No project config found under {PROJECTS}.", file=sys.stderr)
        return 1

    failures = 0
    for path in paths:
        try:
            project = assemble_project(path)
        except ProblemsError:
            print(
                f"SKIP {path}\n     does not load, run "
                f"scripts/validate_configs.py and scripts/validate_projects.py "
                f"to see why.",
                file=sys.stderr,
            )
            failures += 1
            continue

        try:
            km = build_km_bundle(project, created_at=STAMP)
            template = build_template_bundle(project, created_at=STAMP)
        except (ValueError, TypeError, KeyError) as err:
            print(f"FAIL {path}\n     {type(err).__name__}: {err}", file=sys.stderr)
            failures += 1
            continue

        if twice := _duplicate_entities(km):
            print(
                f"FAIL {path}\n     the KM emits {len(twice)} entity(ies) "
                f"twice, first {twice[0]}.",
                file=sys.stderr,
            )
            failures += 1
            continue

        if error := _jinja_error(template):
            print(
                f"FAIL {path}\n     the document template is not Jinja, {error}.",
                file=sys.stderr,
            )
            failures += 1
            continue

        project_id = project.config["id"]
        _write(km_path(project_id), km)
        _write(template_path(project_id), template)

        events = len(km["packages"][0]["events"])
        chars = len(template["files"][0]["content"])
        print(f"ok   {project_id} - {events} events, {chars} chars of Jinja")

    if failures:
        print(
            f"\n{failures} of {len(paths)} projects do not generate.", file=sys.stderr
        )
        return 1

    print(f"\n{len(paths)} projects generate, written under {BUILD_DIR}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
