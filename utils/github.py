"""A GitHub client over the Contents and Git Data APIs, the calls this
repository makes: reading a file, creating one, reading a branch's head and
committing several files at once.

Standard library only, and synchronous.

The transport ends here. Base64, the status codes and the shape of a request
are its business alone, and what it hands out is bytes.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote


class GitHubError(RuntimeError):
    """GitHub rejected a call, or could not be reached at all.

    ``status`` is the HTTP status, or ``None`` when nothing was ever answered.
    """

    def __init__(self, status: int | None, message: str):
        self.status = status
        prefix = f"GitHub API error {status}" if status else "GitHub unreachable"
        super().__init__(f"{prefix}: {message}")


class GitHubClient:
    """One token, against the GitHub API."""

    def __init__(self, token: str, api_url: str = "https://api.github.com"):
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        """The decoded response body, or ``None`` when there is none.

        (!!) Every error status raises, 404 included. On a read a 404 means
        "no such file", on a write it means the write did not happen, and only
        the caller knows which, so the distinction is not made here.

        Failing to reach GitHub raises the same error, without a status, so a
        caller has one exception to handle rather than two. 30 seconds is the
        longest any call waits.
        """
        request = urllib.request.Request(
            self.api_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as e:
            raise GitHubError(e.code, e.read().decode()) from e
        # HTTPError first, it is a subclass of both. This one catches what never
        # became a response: DNS failure, refused connection, timeout.
        except OSError as e:
            raise GitHubError(None, str(e)) from e

    def get_file(self, owner: str, repo: str, path: str) -> bytes | None:
        """What the file says, or ``None`` when there is none there yet.

        (!!) GitHub answers 404 for a repository the token cannot see too, so
        ``None`` means "not there, or not visible with this token".
        """
        try:
            data = self._request("GET", f"/repos/{owner}/{repo}/contents/{path}")
        except GitHubError as e:
            if e.status == 404:
                return None
            raise
        # Past a megabyte the API stops inlining the content and answers with
        # an empty string and `"encoding": "none"`. Decoding that would hand
        # back an empty file as if it were the truth.
        if data.get("encoding") != "base64":
            raise GitHubError(
                200, f"{path}: content not inlined (encoding {data.get('encoding')!r})"
            )
        return base64.b64decode(data["content"])

    def create_file(
        self, owner: str, repo: str, path: str, content: bytes, message: str
    ) -> None:
        """Write ``content`` at ``path``, on the repository's default branch.

        (!!) A creation, and not a replacement. No ``sha`` is sent, so GitHub
        refuses with a 422 when the file is already there rather than
        overwriting it.
        """
        self._request(
            "PUT",
            f"/repos/{owner}/{repo}/contents/{path}",
            {"message": message, "content": base64.b64encode(content).decode()},
        )

    def branch_head(self, owner: str, repo: str, branch: str) -> str | None:
        """The commit a branch points at, or ``None`` when there is no such
        branch."""
        try:
            ref = self._request(
                "GET", f"/repos/{owner}/{repo}/git/ref/heads/{quote(branch, safe='/')}"
            )
        except GitHubError as e:
            if e.status == 404:
                return None
            raise
        return ref["object"]["sha"]

    def commit_files(
        self,
        owner: str,
        repo: str,
        branch: str,
        files: dict[str, bytes],
        message: str,
        parent: str,
    ) -> str:
        """Commit several files onto ``branch``, over ``parent``, and return
        the new commit's sha.

        Four calls of the Git Data API, and only the last one writes: the
        parent commit is read for its tree, a tree is built over it, a commit
        is built over that tree, and the branch reference is moved onto it.
        The files therefore all land or none does, where one call per file
        leaves the branch half written when the second fails.

        ``content`` goes into the tree as text, so every file here must be
        UTF-8.

        (!!) The reference is moved without ``force``. A branch that moved
        between the read of its head and this move makes GitHub refuse, which
        is the wanted answer: the write did not happen, rather than silently
        replacing what moved the branch.
        """
        head = self._request("GET", f"/repos/{owner}/{repo}/git/commits/{parent}")
        tree = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/trees",
            {
                "base_tree": head["tree"]["sha"],
                "tree": [
                    {
                        "path": path,
                        "mode": "100644",
                        "type": "blob",
                        "content": content.decode(),
                    }
                    for path, content in files.items()
                ],
            },
        )
        commit = self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            {"message": message, "tree": tree["sha"], "parents": [parent]},
        )
        self._request(
            "PATCH",
            f"/repos/{owner}/{repo}/git/refs/heads/{quote(branch, safe='/')}",
            {"sha": commit["sha"]},
        )
        return commit["sha"]
