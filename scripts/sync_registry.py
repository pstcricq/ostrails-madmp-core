"""Lay out a registry folder for every project config.

A folder that is not laid out is a folder a submission cannot land in, so this
is the step that makes a project submittable. It needs no DSW instance and
nothing generated, a valid config is enough.

Idempotent, and visibly so, nothing is sent when nothing changed, so a push
that touched no config leaves no commit behind.

Never deletes, and never writes outside a project's own folder.
"""

from __future__ import annotations

import sys
from pathlib import Path

from configs import ConfigFileError, load_config_file
from registry import (
    RegistryError,
    converge,
    registry_from_env,
    token_from_env,
)
from utils.github import GitHubClient, GitHubError

ROOT = Path(__file__).parent.parent
PROJECTS = ROOT / "configs" / "projects"


def main() -> int:
    paths = sorted(PROJECTS.glob("*.yaml"))
    if not paths:
        print(f"No project config found under {PROJECTS}.", file=sys.stderr)
        return 1

    token = token_from_env()
    if not token:
        print(
            "REGISTRY_TOKEN not set, a token with Contents RW on the registry "
            "is needed (in CI a repository secret, locally "
            "REGISTRY_TOKEN=$(gh auth token)).",
            file=sys.stderr,
        )
        return 1

    try:
        registry = registry_from_env()
    except RegistryError as err:
        print(err, file=sys.stderr)
        return 1

    gh = GitHubClient(token=token)
    failures = 0
    verbs: dict[str, int] = {}
    for path in paths:
        try:
            config = load_config_file(path)
        except ConfigFileError:
            print(
                f"SKIP {path.relative_to(ROOT)}\n     does not load, run scripts/validate_configs.py to see why.",
                file=sys.stderr,
            )
            failures += 1
            continue
        try:
            verb = converge(gh, registry, config)
        except GitHubError as err:
            print(f"FAIL {path.relative_to(ROOT)}\n     {err}", file=sys.stderr)
            failures += 1
            continue
        verbs[verb] = verbs.get(verb, 0) + 1
        print(f"{verb:9} {config['id']}")

    if failures:
        print(f"\n{failures} of {len(paths)} projects not registered.", file=sys.stderr)
        return 1

    summary = ", ".join(f"{count} {verb}" for verb, count in sorted(verbs.items()))
    print(f"\n{len(paths)} projects registered ({summary}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
