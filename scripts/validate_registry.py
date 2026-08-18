"""Read every project's destination in the registry and say where it stands.

Reads, and only reads. A folder that is not laid out yet is not a fault,
adding a project is a config first and a registration second, and a sync is
what fixes it. What fails here is a config that does not load, or a registry
that cannot be reached with the token it was given.

Skips, loudly, when no token is set, the registry being private so that even
reading it needs one, and a pull request from a fork will not have it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from configs import ConfigFileError, load_config_file
from registry import (
    GitHubClient,
    GitHubError,
    RegistryError,
    folder_status,
    registry_from_env,
    token_from_env,
)

PROJECTS = Path(__file__).parent.parent / "configs" / "projects"

# Every state FolderStatus can hold: a state added there and forgotten here
# would raise a KeyError on the one run that found it.
MARK = {
    "registered": "ok  ",
    "missing": "todo",
    "stale": "todo",
}


def main() -> int:
    paths = sorted(PROJECTS.glob("*.yaml"))
    if not paths:
        print(f"No project config found under {PROJECTS}.", file=sys.stderr)
        return 1

    token = token_from_env()
    if not token:
        print(
            "REGISTRY_TOKEN not set, skipping. The registry is private, so "
            "even reading it needs a token (locally: "
            "REGISTRY_TOKEN=$(gh auth token)).",
            file=sys.stderr,
        )
        return 0

    try:
        registry = registry_from_env()
    except RegistryError as err:
        print(err, file=sys.stderr)
        return 1

    gh = GitHubClient(token=token)
    faults = 0
    for path in paths:
        try:
            config = load_config_file(path)
        except ConfigFileError:
            print(
                f"SKIP {path}\n     does not load, run scripts/validate_configs.py to see why.",
                file=sys.stderr,
            )
            faults += 1
            continue
        try:
            status = folder_status(gh, registry, config)
        except GitHubError as err:
            print(f"FAIL {path}\n     {err}", file=sys.stderr)
            faults += 1
            continue

        print(f"{MARK[status.state]} {status.folder} - {status.detail}")

    if faults:
        print(
            f"\n{faults} of {len(paths)} destinations could not be read.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{len(paths)} projects, every destination read.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
