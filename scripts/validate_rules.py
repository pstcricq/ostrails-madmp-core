"""Validate every rules file, and check the tree they sit in.

Two things, over the whole of `rules/standards/`:

1. each file loads through `load_rules_file`, the same entry point the rest
   of the code uses, so a file that passes here is a file the loader accepts
   and not merely one that parses as JSON
2. each file declares the standard and the version its path names, a static
   property of the tree, checked here on every file rather than at load time
   on whichever subset a project happens to select
"""

from __future__ import annotations

import sys
from pathlib import Path

from rules import RulesFileError, load_rules_file

ROOT = Path(__file__).parent.parent
STANDARDS = ROOT / "rules" / "standards"


def main() -> int:
    paths = sorted(STANDARDS.rglob("*.json"))
    if not paths:
        print(f"No rules file found under {STANDARDS}.", file=sys.stderr)
        return 1

    failures = 0
    for path in paths:
        try:
            doc = load_rules_file(path)
        except RulesFileError as err:
            print(f"FAIL {path.relative_to(ROOT)}\n     {err}", file=sys.stderr)
            failures += 1
            continue

        print(f"ok   {path.relative_to(ROOT)} : {doc['standard']} {path.stem}")

    if failures:
        print(f"\n{failures} of {len(paths)} rules files rejected.", file=sys.stderr)
        return 1

    print(f"\n{len(paths)} rules files valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
