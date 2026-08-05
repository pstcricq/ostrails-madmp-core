"""Check that every project names rules that exist, and that they hold together.

The one check that crosses the data packages. `validate_rules.py` and
`validate_configs.py` each stay inside their own, which is what makes them
legible — and what leaves a hole between them: a config pinning a version
nobody ever wrote passes both. Here every `configs/projects/*.yaml` is loaded
the way a generator will load it, through `assemble_project`: its pins resolved
against `rules/standards/`, and the files behind them merged.

Whether a *file* is well formed stays the other jobs' answer, and they check
every file in the tree, so anything pinned here is already known good on its
own. What no per-file job can see is the *set*: two pinned standards
disagreeing on a shared field is a property of the combination. The unit tests
merge the real standards too, but from a list written in the test — this is the
only place the set a project actually pins gets merged, so bumping a pin or
adding a standard is covered by the same check that covers writing them.

It calls `assemble_project` rather than resolving and merging itself, which is the
whole point of that function existing: the CI checks what a generator will
get, not a sequence that resembles it.

Runs beside the other jobs rather than after them, deliberately: a project
whose pins do not resolve is broken whether or not some other file is also
broken, and gating this behind them would cost a second push to find out. A
config this script cannot even load is handed back to the `configs` job, which
says why, rather than having its verdict reprinted here.
"""

from __future__ import annotations

import sys
from pathlib import Path

from configs import ConfigFileError
from project import assemble_project
from utils.errors import ProblemsError

ROOT = Path(__file__).parent.parent
PROJECTS = ROOT / "configs" / "projects"


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
                f"SKIP {path}\n     does not load; the configs job says why.",
                file=sys.stderr,
            )
            failures += 1
            continue
        except ProblemsError as err:  # unresolved pins, ill-formed or conflicting set
            details = "\n".join(f"       - {problem}" for problem in err.problems)
            print(f"FAIL {path}\n{details}", file=sys.stderr)
            failures += 1
            continue

        merged = " + ".join(project.model.standards)
        fields = sum(1 for _ in project.model.walk())
        print(f"ok   {path} - {merged} -> {fields} fields")

    if failures:
        print(f"\n{failures} of {len(paths)} projects rejected.", file=sys.stderr)
        return 1

    print(f"\n{len(paths)} projects resolve and merge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
