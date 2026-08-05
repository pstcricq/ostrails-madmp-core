"""Check that every project's registry destination is free, or already its own.

Reads, and only reads. The one fault it can find is a **collision**: a folder
that carries another project's `id`, which no amount of syncing fixes and
which would have one project's DMPs land in another's folder.

A folder that does not exist yet is *not* a fault. Adding a project is a
config first and a registration second, and failing the check on the very push
that adds it would teach everyone to ignore this job. Same for a `meta.yaml`
that no longer says what its config says: the sync on the default branch is
what fixes that, and it runs right after this.

Skips, loudly, when no token is set: the registry is private, so even reading
it needs one, and a pull request from a fork will not have it. The authority
is `sync_registry.py`, which refuses to skip.
"""

from __future__ import annotations

import sys
from pathlib import Path

from configs import ConfigFileError, load_config_file
from registry import GitHubClient, GitHubError, folder_status, token_from_env

PROJECTS = Path(__file__).parent.parent / "configs" / "projects"

MARK = {
    "registered": "ok  ",
    "missing": "todo",
    "stale": "todo",
    "collision": "FAIL",
}


def main() -> int:
    paths = sorted(PROJECTS.glob("*.yaml"))
    if not paths:
        print(f"No project config found under {PROJECTS}.", file=sys.stderr)
        return 1

    token = token_from_env()
    if not token:
        print(
            "REGISTRY_TOKEN not set — skipping. The registry is private, so "
            "even reading it needs a token (locally: "
            "REGISTRY_TOKEN=$(gh auth token)).",
            file=sys.stderr,
        )
        return 0

    gh = GitHubClient(token=token)
    faults = 0
    for path in paths:
        try:
            config = load_config_file(path)
        except ConfigFileError:
            print(
                f"SKIP {path}\n     does not load; the configs job says why.",
                file=sys.stderr,
            )
            faults += 1
            continue
        try:
            status = folder_status(gh, config)
        except GitHubError as err:
            print(f"FAIL {path}\n     {err}", file=sys.stderr)
            faults += 1
            continue

        line = f"{MARK[status.state]} {status.folder} - {status.detail}"
        if status.is_fault:
            faults += 1
            print(line, file=sys.stderr)
        else:
            print(line)

    if faults:
        print(
            f"\n{faults} of {len(paths)} projects cannot be registered.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{len(paths)} projects, no destination taken by anyone else.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
