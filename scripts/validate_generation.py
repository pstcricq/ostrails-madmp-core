"""Build every project's KM and Document Template under ``build/``.

Two things at once, and both are the point.

**A verdict.** The unit tests generate one project deeply — every kind of
question, every refusal, the invariants that bind the two artifacts together.
What they cannot do is generate *the others*: a second project's rules,
vocabularies and pins are data no test has seen. This is the only place every
config goes through the generators, and a repository that cannot generate one
of its projects is broken whether or not anyone has asked for that project's
KM yet.

So what it checks is what the data decides rather than what the code decides:
that the KM emits no entity twice, and that the document template is Jinja at
all. Both are questions only this project's vocabularies can answer, and both
would otherwise be answered by DSW — the first by dropping a question, the
second at render time in front of a researcher.

**The artifacts.** What it writes is uploaded by CI as a workflow artifact,
which is how a reviewer sees what a rules change did to the questionnaire, and
how the publish step gets the bundles it ships. They are therefore stamped
with the real time: a frozen timestamp would be a false creation date carried
into every published package.

Depends on nothing outside this repository — generation reads the config and
the rules, and touches neither DSW nor the registry. Which is why it runs in
parallel with the other checks, and why `registry-sync` waits for it rather
than the other way round: writing anywhere is what has to wait.
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
    """Entities the KM emits twice — DSW would apply the second event on top of
    the first and one of the two questions would simply not be there.

    Data-dependent, which is why it is checked per config rather than once in
    the tests: `uuids.other_answer_uuid(path)` is by construction
    `answer_uuid(path, "other")`, so a standard whose vocabulary lists the word
    literally collides with the synthetic "Other". None does today.
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
    DSW would notice a syntax error — DSW would, at render time, in front of a
    researcher. The unit tests parse one project's body; what they cannot parse
    is a body built from vocabularies they have never seen.

    Data-dependent for the same reason the duplicate check is, and for a
    sharper one: a vocabulary label is not only data the template reads, it is
    *source* the generator writes — the answer-label table holds each one as a
    Jinja literal. `Institut d'Optique` used to close its literal early and
    leave a body that was not Jinja at all.
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
                f"SKIP {path}\n     does not load; the configs and projects "
                f"jobs say why.",
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
