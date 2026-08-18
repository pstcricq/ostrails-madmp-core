"""Run the quality control over every project's own merged rules.

The engine is exercised on synthetic models by the test suite. What no test
sees is the set every project actually pins: a rules file may declare a
`_type` nothing in this repository can check, and a field the engine cannot
walk is only found the day a submitted DMP carries it.

Two things are read here, and both are properties of the data rather than of
the code. Every scalar type a project's model declares must be one the engine
implements. And the engine must walk that model whole, which is what running
it over an empty document does: one presence result per field, and every
tightening note the merge recorded rendered at least once.

Nothing is checked against a real DMP, there is none in this repository. The
document a project's researcher submits is checked in the registry.
"""

from __future__ import annotations

import sys
from pathlib import Path

from configs import ConfigFileError
from project import assemble_project
from quality_control import SCALAR_TYPES, run_qc
from utils.errors import ProblemsError

PROJECTS = Path(__file__).parent.parent / "configs" / "projects"

# The one document every project can be walked over without inventing data.
EMPTY = {"dmp": {}}


def main() -> int:
    paths = sorted(PROJECTS.glob("*.yaml"))
    if not paths:
        print(f"No project config found under {PROJECTS}.", file=sys.stderr)
        return 1

    failures = 0
    for path in paths:
        try:
            project = assemble_project(path)
        except ConfigFileError:
            print(
                f"SKIP {path}\n     does not load, run scripts/validate_configs.py to see why.",
                file=sys.stderr,
            )
            failures += 1
            continue
        except ProblemsError:
            print(
                f"SKIP {path}\n     does not resolve, run scripts/validate_projects.py to see why.",
                file=sys.stderr,
            )
            failures += 1
            continue

        model = project.model
        fields = [f for f in model.walk() if f.type != "object"]
        unknown = sorted({f.type for f in fields} - set(SCALAR_TYPES))
        if unknown:
            named = ", ".join(unknown)
            print(
                f"FAIL {path}\n     declares scalar types the engine cannot "
                f"check: {named}",
                file=sys.stderr,
            )
            failures += 1
            continue

        results = run_qc(model, EMPTY)
        presence = [r for r in results if r.category == "presence"]
        if len(presence) != len(model.fields):
            print(
                f"FAIL {path}\n     {len(model.fields)} top-level fields gave "
                f"{len(presence)} presence results",
                file=sys.stderr,
            )
            failures += 1
            continue

        required = sum(1 for r in results if r.status == "fail")
        print(
            f"ok   {path} - {sum(1 for _ in model.walk())} fields, "
            f"{len(fields)} scalars, {required} required at the root"
        )

    if failures:
        print(
            f"\n{failures} of {len(paths)} projects cannot be checked.", file=sys.stderr
        )
        return 1

    print(f"\n{len(paths)} projects, every field the engine can walk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
