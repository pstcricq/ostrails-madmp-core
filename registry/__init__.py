"""Public API of a project's destination in the dmp-registry mono-repo.

What this package owns is making sure the folder a submitted DMP lands in
exists, is laid out, and is this project's.

``projects/<id>/`` holds ``meta.yaml``, ``template/`` where the DMP is
dropped, and ``productions/``.

- ``github.py`` is the transport, two calls of the GitHub Contents API
- ``folder.py`` reads a project's folder and converges it

One condition for a module to belong here: nothing else in this repository
calls GitHub. A module that does not, or that would have another caller here,
does not belong.
"""

from registry.folder import (
    FolderStatus,
    Registry,
    RegistryError,
    converge,
    folder_status,
    meta_document,
    registry_from_env,
    token_from_env,
)
from registry.github import GitHubClient, GitHubError

__all__ = [
    "FolderStatus",
    "GitHubClient",
    "GitHubError",
    "Registry",
    "RegistryError",
    "converge",
    "folder_status",
    "meta_document",
    "registry_from_env",
    "token_from_env",
]
