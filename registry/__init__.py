"""Public API of a project's destination in the registry mono-repo.

What this package owns is making sure the folder a submitted DMP lands in
exists and is laid out.

``projects/<id>/`` holds ``template/`` where the DMP is dropped, and
``productions/``.

``folder.py`` is the whole of it, reading a project's folder and converging
it over a client from ``utils.github``.

One condition for a module to belong here: it says what a project's folder is
made of. Nothing else has a place in it.
"""

from registry.folder import (
    FolderStatus,
    Registry,
    RegistryError,
    converge,
    folder_status,
    registry_from_env,
    token_from_env,
)

__all__ = [
    "FolderStatus",
    "Registry",
    "RegistryError",
    "converge",
    "folder_status",
    "registry_from_env",
    "token_from_env",
]
