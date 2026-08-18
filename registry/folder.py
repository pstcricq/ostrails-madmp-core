"""One project's folder in the registry, and how it gets there.

Two verbs. ``folder_status()`` only ever reads, and answers whether the
project's destination is laid out. ``converge()`` writes, and is the act of
registering.

A folder is its two subdirectories, and both verbs read both.

Converging is idempotent, nothing is sent when nothing changed, and the verb
it returns says what it sent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from registry.github import GitHubClient
from utils.errors import ProblemsError

# The two directories a project's folder holds, `template/` for the submitted
# DMP and `productions/` for the deployment DMPs derived from it. Git stores
# no empty directory, so each is created holding a .gitkeep.
SUBDIRS = ("template", "productions")


class RegistryError(ProblemsError):
    """A project cannot be registered, the registry to write to is not named."""

    noun = "registry problem"


@dataclass(frozen=True)
class FolderStatus:
    """What one read of the registry found.

    ``state`` is one of ``"registered"`` (both subdirectories are laid out),
    ``"stale"`` (one of the two is not) or ``"missing"`` (neither is, so
    there is no folder at all).
    """

    folder: str
    state: str
    detail: str


@dataclass(frozen=True)
class Registry:
    """Which mono-repo a project's folder lives in.

    A value, not a constant, read from the environment with no default, so no
    deployment can write into another's registry by omission.
    """

    owner: str
    repo: str


def registry_from_env() -> Registry:
    """Which registry this deployment writes to, or every name it is missing
    at once."""
    names = ("REGISTRY_OWNER", "REGISTRY_REPO")
    values = [os.environ.get(name) for name in names]
    missing = [name for name, value in zip(names, values, strict=True) if not value]
    if missing:
        raise RegistryError(
            [
                f"{name} is not set, it says which registry to write to."
                for name in missing
            ]
        )
    return Registry(*values)


def token_from_env() -> str | None:
    """The token, or ``None``. ``REGISTRY_TOKEN`` is the only name accepted.
    Locally, ``REGISTRY_TOKEN=$(gh auth token)``, which leaves it nowhere.

    Absent is not an error here, one caller skips and the other refuses.

    No fallback on ``GITHUB_TOKEN``. A workflow's default token is scoped to
    the repository running it, not to the registry, and a token without access
    reads as 404, which a GET turns into "no file yet", so falling back would
    report a project missing when the truth is a wrong token.
    """
    return os.environ.get("REGISTRY_TOKEN")


def folder_path(config: dict[str, Any]) -> str:
    """Where this project's folder is, named after the config's ``id``."""
    return f"projects/{config['id']}"


def keep_path(config: dict[str, Any], subdir: str) -> str:
    """Where a subdirectory's ``.gitkeep`` lives, the file that makes the
    subdirectory exist."""
    return f"{folder_path(config)}/{subdir}/.gitkeep"


def _absent_subdirs(
    gh: GitHubClient, registry: Registry, config: dict[str, Any]
) -> list[str]:
    """Which of the two subdirectories are not laid out yet."""
    return [
        sub
        for sub in SUBDIRS
        if gh.get_file(registry.owner, registry.repo, keep_path(config, sub)) is None
    ]


def folder_status(
    gh: GitHubClient, registry: Registry, config: dict[str, Any]
) -> FolderStatus:
    """Read this project's folder and say where it stands. Writes nothing."""
    folder = config["id"]
    absent = _absent_subdirs(gh, registry, config)
    if len(absent) == len(SUBDIRS):
        return FolderStatus(
            folder, "missing", "no folder yet, it is created on the default branch."
        )
    if absent:
        return FolderStatus(
            folder,
            "stale",
            f"{', '.join(sub + '/' for sub in absent)} not laid out, "
            f"brought up to date on the default branch.",
        )
    return FolderStatus(folder, "registered", "both subdirectories are laid out.")


def converge(gh: GitHubClient, registry: Registry, config: dict[str, Any]) -> str:
    """Lay out this project's folder, and return what that took, ``"created"``,
    ``"updated"`` or ``"unchanged"``.

    Writes the ``.gitkeep`` files that are absent and nothing else. Never
    deletes, and never writes outside this project's own folder.
    """
    absent = _absent_subdirs(gh, registry, config)
    for subdir in absent:
        gh.put_file(
            registry.owner,
            registry.repo,
            keep_path(config, subdir),
            b"",
            f"register: {config['id']} {subdir}/",
        )
    if not absent:
        return "unchanged"
    return "created" if len(absent) == len(SUBDIRS) else "updated"
