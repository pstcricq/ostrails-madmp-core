"""One project's folder in the registry: what it must say, and how it gets
there.

Two verbs, deliberately separate. :func:`folder_status` only ever reads — it
answers "is this project's destination there, and is it this project's?", a
question about the project that anyone can ask from any branch.
:func:`converge` writes, and *is* the act of registering: until it has run, a
researcher clicking Submit in DSW is turned away, because the webhook refuses
a folder with no ``meta.yaml``.

Converging is idempotent, and **observably** so: nothing is sent when nothing
changed, so a job running on every push to the default branch leaves no commit
behind every time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

from registry.github import GitHubClient
from utils.errors import ProblemsError

# The two directories a project's folder holds: `template/`, where the webhook
# drops the submitted DMP, and `productions/`, for the deployment DMPs derived
# from it. Both are ours to create — the webhook only writes a document into a
# folder that is already laid out. Git stores no empty directory, so each is
# created holding a .gitkeep.
SUBDIRS = ("template", "productions")

# The keys of `meta.yaml` this repository owns. Everything else found in the
# file belongs to somebody else — the registry's own CI, today or tomorrow —
# and is carried across untouched and never compared. Rebuilding the file from
# the config alone would erase their work silently, and comparing on their
# keys would make us fight them for the file.
OWNED = ("id", "rules")


class RegistryError(ProblemsError):
    """A project cannot be registered where its config says."""

    noun = "registry problem"


@dataclass(frozen=True)
class FolderStatus:
    """What one read of the registry found.

    ``state`` is one of ``"registered"`` (there, it is this project's, and it
    says what the config says), ``"stale"`` (this project's, but no longer
    saying it), ``"missing"`` (nothing there yet) or ``"collision"`` (there,
    and it is another project's).
    """

    folder: str
    state: str
    detail: str

    @property
    def is_fault(self) -> bool:
        """Whether this state is somebody's mistake rather than a step not
        taken yet. Only a collision is: two projects claiming one destination
        cannot both be right, and no amount of syncing fixes it."""
        return self.state == "collision"


@dataclass(frozen=True)
class Registry:
    """Which mono-repo a project's folder lives in.

    A value, not a constant, and read from the environment with **no default**.
    A default owner and repo would be one deployment's coordinates baked into
    every other's: a fork, a colleague's checkout or a misconfigured job would
    write into this deployment's registry without anyone having said so. Where
    a program writes is not something it may assume.
    """

    owner: str
    repo: str


def registry_from_env() -> Registry:
    """Which registry this deployment writes to, or every name it is missing
    at once — a half-configured environment is fixed faster from the whole
    list."""
    names = ("REGISTRY_OWNER", "REGISTRY_REPO")
    values = [os.environ.get(name) for name in names]
    missing = [name for name, value in zip(names, values, strict=True) if not value]
    if missing:
        raise RegistryError(
            [
                f"{name} is not set; it says which registry to write to."
                for name in missing
            ]
        )
    return Registry(*values)


def token_from_env() -> str | None:
    """The token, or ``None``. ``REGISTRY_TOKEN`` is the name the whole
    deployment uses — the submission webhook reads the same one — and the only
    name accepted. Locally: ``REGISTRY_TOKEN=$(gh auth token)``, which leaves
    it nowhere.

    Absent, it is not an error here: one caller skips and the other refuses,
    and only they know which. That is why this is the one name read without
    :func:`registry_from_env` raising on it.

    **No fallback on ``GITHUB_TOKEN``, deliberately.** A workflow's default
    token is scoped to the repository running it, not to the registry, so it
    could never do this job; and a token without access reads as 404, which
    :mod:`registry.github` turns into "no file yet" on a GET. Falling back
    would report a project ``missing`` when the truth is a wrong token —
    green, and wrong, exactly where there is no write to catch it.
    """
    return os.environ.get("REGISTRY_TOKEN")


def folder_path(config: dict[str, Any]) -> str:
    """Where this project's folder is. ``id`` is the folder name: one string
    names the config file, the registry folder and the DSW packages, so there
    is nothing here to keep in step with anything."""
    return f"projects/{config['id']}"


def meta_path(config: dict[str, Any]) -> str:
    return f"{folder_path(config)}/meta.yaml"


def meta_document(
    config: dict[str, Any], previous: dict[str, Any] | None = None
) -> dict[str, Any]:
    """What ``meta.yaml`` must say: who the project is, and the rules versions
    it was built from.

    The pins are the reason the file exists. A DMP has to be checkable against
    the very rules it was built with, and a config's pins move; frozen here at
    registration, they stay readable long after. Nothing reads them yet — the
    quality control that will is not built — but they cannot be added later,
    since no one could then say what was pinned when a given DMP was submitted.

    ``previous`` is the document being replaced, and everything in it that is
    not ours is carried across in the order it was found.
    """
    document = {"id": config["id"], "rules": config["rules"]}
    document.update(
        {key: value for key, value in (previous or {}).items() if key not in OWNED}
    )
    return document


def meta_bytes(document: dict[str, Any]) -> bytes:
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode()


def _read_meta(
    gh: GitHubClient, registry: Registry, config: dict[str, Any]
) -> tuple[Any, dict | None]:
    """The file and the document it parses to, or ``(None, None)``."""
    entry = gh.get_file(registry.owner, registry.repo, meta_path(config))
    if entry is None:
        return None, None
    return entry, yaml.safe_load(entry.content)


def folder_status(
    gh: GitHubClient, registry: Registry, config: dict[str, Any]
) -> FolderStatus:
    """Read this project's folder and say where it stands. Writes nothing."""
    folder = config["id"]
    _, current = _read_meta(gh, registry, config)
    if current is None:
        return FolderStatus(
            folder, "missing", "no folder yet; it is created on the default branch."
        )
    if current.get("id") != config["id"]:
        return FolderStatus(
            folder,
            "collision",
            f"{folder_path(config)}/ belongs to project {current.get('id')!r}, "
            f"not {config['id']!r}.",
        )
    if meta_document(config, current) != current:
        return FolderStatus(
            folder,
            "stale",
            "meta.yaml no longer says what the config says; it is updated on "
            "the default branch.",
        )
    return FolderStatus(folder, "registered", "meta.yaml says what the config says.")


def converge(gh: GitHubClient, registry: Registry, config: dict[str, Any]) -> str:
    """Make the registry say what the config says, and return what that took:
    ``"created"``, ``"updated"`` or ``"unchanged"``.

    Never deletes and never overwrites another project: a collision raises
    rather than clobbering a folder somebody else's DMPs land in.

    What decides between updating and doing nothing is the **document**, not
    the bytes. A file that says the right thing with its keys in another order,
    or written by another YAML dumper, is already right, and rewriting it would
    be a commit that changes nothing anyone can read.
    """
    entry, current = _read_meta(gh, registry, config)
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
    if current is None:
        verb = "created"
    elif wanted == current:
        verb = "unchanged"
    else:
        verb = "updated"

    if verb != "unchanged":
        gh.put_file(
            registry.owner,
            registry.repo,
            meta_path(config),
            meta_bytes(wanted),
            f"register: {config['id']} meta.yaml",
            sha=entry.sha if entry else None,
        )
    for sub in SUBDIRS:
        keep = f"{folder_path(config)}/{sub}/.gitkeep"
        if gh.get_file(registry.owner, registry.repo, keep) is None:
            gh.put_file(
                registry.owner,
                registry.repo,
                keep,
                b"",
                f"register: {config['id']} {sub}/",
            )
    return verb
