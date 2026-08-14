"""One project's folder in the registry, what it must say and how it gets
there.

Two verbs. ``folder_status()`` only ever reads, and answers whether the
project's destination is there and is this project's. ``converge()`` writes,
and is the act of registering.

Both are about the same folder: a folder is ``meta.yaml`` and its two
subdirectories, and both verbs read all three.

Converging is idempotent, nothing is sent when nothing changed, and the verb
it returns says what it sent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

from registry.github import GitHubClient
from utils.errors import ProblemsError

# The two directories a project's folder holds, `template/` for the submitted
# DMP and `productions/` for the deployment DMPs derived from it. Git stores
# no empty directory, so each is created holding a .gitkeep.
SUBDIRS = ("template", "productions")

# The keys of `meta.yaml` this repository owns. Everything else found in the
# file belongs to another writer and is carried across untouched, never
# compared, so a converge neither erases it nor fights over it.
OWNED = ("id", "rules")


class RegistryError(ProblemsError):
    """A project cannot be registered where its config says."""

    noun = "registry problem"


@dataclass(frozen=True)
class FolderStatus:
    """What one read of the registry found.

    ``state`` is one of ``"registered"`` (there, it is this project's, and it
    says what the config says), ``"stale"`` (this project's, but no longer
    saying it), ``"missing"`` (nothing there yet), ``"collision"`` (there, and
    it is another project's) or ``"unreadable"`` (there, and not a document).
    """

    folder: str
    state: str
    detail: str

    @property
    def is_fault(self) -> bool:
        """Whether this state is somebody's mistake rather than a step not
        taken yet.

        Two are, a collision and an unreadable ``meta.yaml``. Neither is
        resynced, both take a human.
        """
        return self.state in ("collision", "unreadable")


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


def meta_path(config: dict[str, Any]) -> str:
    """Where this project's ``meta.yaml`` lives."""
    return f"{folder_path(config)}/meta.yaml"


def meta_document(
    config: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    """What ``meta.yaml`` must say, who the project is and the rules versions
    it was built from.

    The pins are frozen here at registration, so a DMP stays checkable against
    the very rules it was built with.

    ``previous`` is the document being replaced, and everything in it that is
    not ours is carried across in the order it was found.
    """
    document = {"id": config["id"], "rules": config["rules"]}
    document.update(
        {key: value for key, value in (previous or {}).items() if key not in OWNED}
    )
    return document


def meta_bytes(document: dict[str, Any]) -> bytes:
    """The document as the bytes written to the registry."""
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode()


class UnreadableMeta(Exception):
    """``meta.yaml`` is there and cannot be read as a document.

    Not a ``RegistryError``, the two verbs answer for it differently, one
    reports a state and the other refuses. Internal to this module, so it
    carries a reason rather than a problem list.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _read_meta(
    gh: GitHubClient, registry: Registry, config: dict[str, Any]
) -> tuple[Any, dict | None]:
    """The file and the document it parses to, or ``(None, None)`` when there
    is no file. Raises ``UnreadableMeta`` when there is one and it is not a
    document.

    Three outcomes, not two. Reporting a damaged ``meta.yaml`` as no file at
    all would have it rebuilt from the config alone, dropping whatever another
    writer had recorded in it.
    """
    entry = gh.get_file(registry.owner, registry.repo, meta_path(config))
    if entry is None:
        return None, None
    try:
        document = yaml.safe_load(entry.content)
    except yaml.YAMLError as err:
        raise UnreadableMeta(f"invalid YAML: {err}") from err
    if not isinstance(document, dict):
        # An empty file parses to None, a list or a scalar to something with
        # no keys to read. None of them can be compared or safely overwritten.
        found = "empty" if document is None else f"a {type(document).__name__}"
        raise UnreadableMeta(f"not a mapping ({found}).")
    return entry, document


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
    try:
        _, current = _read_meta(gh, registry, config)
    except UnreadableMeta as err:
        return FolderStatus(
            folder,
            "unreadable",
            # The reason last, a YAML parse error is several lines and a
            # sentence continuing after it would be read by nobody.
            f"{meta_path(config)} is there and cannot be read, so it can "
            f"neither be compared nor overwritten by this job, {err.reason}",
        )
    if current is None:
        return FolderStatus(
            folder, "missing", "no folder yet, it is created on the default branch."
        )
    if current.get("id") != config["id"]:
        return FolderStatus(
            folder,
            "collision",
            f"{folder_path(config)}/ belongs to project {current.get('id')!r}, "
            f"not {config['id']!r}.",
        )

    # Everything out of date at once, both are fixed by the same sync.
    outdated = []
    if meta_document(config, current) != current:
        outdated.append("meta.yaml no longer says what the config says")
    if absent := _absent_subdirs(gh, registry, config):
        outdated.append(f"{', '.join(sub + '/' for sub in absent)} not laid out")
    if outdated:
        return FolderStatus(
            folder,
            "stale",
            f"{'; '.join(outdated)}; brought up to date on the default branch.",
        )
    return FolderStatus(folder, "registered", "the folder says what the config says.")


def converge(gh: GitHubClient, registry: Registry, config: dict[str, Any]) -> str:
    """Make the registry say what the config says, and return what that took,
    ``"created"``, ``"updated"`` or ``"unchanged"``.

    The verb answers for the folder, from what was actually sent, so a
    ``.gitkeep`` put back is an update whatever ``meta.yaml`` had to say.

    Never deletes and never overwrites another project, a collision raises,
    and so does a ``meta.yaml`` that is there and does not parse.

    What decides between updating and doing nothing is the document, not the
    bytes, so keys in another order or another dumper's output are already
    right.
    """
    try:
        entry, current = _read_meta(gh, registry, config)
    except UnreadableMeta as err:
        raise RegistryError(
            [
                (
                    f"{meta_path(config)} is there and cannot be read. "
                    f"Rewriting it would drop the rules pins this project's "
                    f"submitted DMPs are checked against, and any key another "
                    f"writer owns. Fix the file by hand, {err.reason}"
                )
            ],
            folder_path(config),
        ) from err
    if current is not None and current.get("id") != config["id"]:
        raise RegistryError(
            [
                (
                    f"already belongs to project {current.get('id')!r}, not "
                    f"{config['id']!r}."
                )
            ],
            folder_path(config),
        )

    wanted = meta_document(config, current)
    sent = False
    if current is None or wanted != current:
        gh.put_file(
            registry.owner,
            registry.repo,
            meta_path(config),
            meta_bytes(wanted),
            f"register: {config['id']} meta.yaml",
            sha=entry.sha if entry else None,
        )
        sent = True
    for sub in _absent_subdirs(gh, registry, config):
        gh.put_file(
            registry.owner,
            registry.repo,
            keep_path(config, sub),
            b"",
            f"register: {config['id']} {sub}/",
        )
        sent = True

    if current is None:
        return "created"
    return "updated" if sent else "unchanged"
