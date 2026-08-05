"""Make the registry say what every project config says.

The step that makes a submission possible at all: the webhook refuses a folder
with no `meta.yaml`, so until this has run, a researcher clicking Submit is
turned away. It needs no DSW instance and nothing generated — a valid config
is enough, which is why it comes before anything is published.

Runs on the default branch only, and on every push to it rather than only when
a config changed. `meta.yaml` freezes the rules versions a project was built
from, and the failure worth preventing is drift: a pin bumped in the config
while the registry still names the old version. Converging every time closes
that by construction.

Idempotent, and visibly so: nothing is sent when nothing changed, so this
leaves no commit behind on a push that touched no config.

Never deletes, never overwrites another project's folder, and never touches a
key it does not own — whatever else `meta.yaml` carries is carried across.
"""

from __future__ import annotations

import sys
from pathlib import Path

from configs import ConfigFileError, load_config_file
from registry import (
    GitHubClient,
    GitHubError,
    RegistryError,
    converge,
    registry_from_env,
    token_from_env,
)

PROJECTS = Path(__file__).parent.parent / "configs" / "projects"


def main() -> int:
    paths = sorted(PROJECTS.glob("*.yaml"))
    if not paths:
        print(f"No project config found under {PROJECTS}.", file=sys.stderr)
        return 1

    token = token_from_env()
    if not token:
        print(
            "REGISTRY_TOKEN not set — need a token with Contents RW on the "
            "registry (in CI: a repository secret; locally: "
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
                f"SKIP {path}\n     does not load; the configs job says why.",
                file=sys.stderr,
            )
            failures += 1
            continue
        try:
            verb = converge(gh, registry, config)
        except (RegistryError, GitHubError) as err:
            print(f"FAIL {path}\n     {err}", file=sys.stderr)
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
