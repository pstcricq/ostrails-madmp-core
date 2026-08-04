"""Validate every project config, and check the tree they sit in.

Two things, over the whole of `configs/projects/`:

1. each file loads through `load_config_file` — the same entry point the rest of
   the code uses, so a file that passes here is a file the loader accepts,
   not merely one that parses as YAML;
2. each file's name agrees with the id it declares. That is a static property of
   the tree, so it is checked here, on every file, rather than at load time on
   whichever config a run happens to select.

A script rather than inline workflow YAML, for the reason
`scripts/validate_rules.py` gives: a check that only exists inside the
workflow gets debugged by push-and-wait.
"""

from __future__ import annotations

import sys
from pathlib import Path

from configs import ConfigFileError, load_config_file

PROJECTS = Path(__file__).parent.parent / "configs" / "projects"


def main() -> int:
    paths = sorted(PROJECTS.glob("*.yaml"))
    if not paths:
        print(f"No project config found under {PROJECTS}.", file=sys.stderr)
        return 1

    failures = 0
    for path in paths:
        try:
            config = load_config_file(path)
        except ConfigFileError as err:
            print(f"FAIL {path}\n     {err}", file=sys.stderr)
            failures += 1
            continue

        print(f"ok   {path} - {config['id']} {config['version']}")

    if failures:
        print(
            f"\n{failures} of {len(paths)} project configs rejected.", file=sys.stderr
        )
        return 1

    print(f"\n{len(paths)} project configs valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
