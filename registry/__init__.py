"""Public API of a project's destination in the dmp-registry mono-repo.

A DMP is not published there — it is *submitted* there, by a webhook, when a
researcher clicks Submit in DSW. What this package owns is the step before:
making sure the folder that submission will land in exists, is laid out, and
is this project's.

``projects/<id>/`` holds ``meta.yaml``, ``template/`` where the webhook drops
the DMP, and ``productions/``. Laying it out is ours, not the webhook's: the
webhook writes one document into a folder, and refuses a folder with no
``meta.yaml`` — an uninitialized folder means no rules pins, so a DMP dropped
there would be an orphan. The registry's own README is the contract between
the two sides, and neither may drift from it.

This has nothing to do with DS Wizard, which is why it is not in ``dsw/``: it
needs no DSW instance, no published package, nothing generated. A valid config
is enough, which is why registering comes straight after validation.
``dsw/`` will know the DSW API and carry its own client; this package knows
the GitHub Contents API and carries its own — ``utils/`` is for what *several*
packages share, and this is shared with nobody.

**The rule this package refuses an addition by: nothing else in this
repository calls GitHub.** A module that does not, or that would have another
caller here, does not belong.
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
