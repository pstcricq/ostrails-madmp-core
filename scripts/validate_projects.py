"""Check that every project names rules that exist, and that they hold together.

The one check that crosses the data packages. A config pinning a version
nobody ever wrote passes every per-file check there is, so here every
``configs/projects/*.yaml`` is loaded the way a generator will load it, through
``assemble_project``, its pins resolved against ``rules/standards/`` and the files
behind them merged.

Whether a file is well formed is answered file by file elsewhere. What no
per-file check can see is the set: two pinned standards disagreeing on a
shared field is a property of the combination, and this is the only place the
set a project actually pins gets merged, so bumping a pin or adding a standard
is covered by the same check that covers writing them.
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
                f"SKIP {path.relative_to(ROOT)}\n     does not load, run scripts/validate_configs.py to see why.",
                file=sys.stderr,
            )
            failures += 1
            continue
        except ProblemsError as err:  # unresolved pins, ill-formed or conflicting set
            details = "\n".join(f"       - {problem}" for problem in err.problems)
            print(f"FAIL {path.relative_to(ROOT)}\n{details}", file=sys.stderr)
            failures += 1
            continue

        merged = " + ".join(project.model.standards)
        fields = sum(1 for _ in project.model.walk())
        print(f"ok   {path.relative_to(ROOT)} : {merged}, {fields} fields")

    if failures:
        print(f"\n{failures} of {len(paths)} projects rejected.", file=sys.stderr)
        return 1

    print(f"\n{len(paths)} projects resolve and merge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
