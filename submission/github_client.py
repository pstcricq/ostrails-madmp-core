"""Thin GitHub client: reading a file, and committing several at once.

Synchronous and stdlib-only. The blocking call is the reason app.py hands
handle_submission to a thread pool rather than awaiting it: run from the event
loop, the wait below would freeze the whole process, /health included.

Kept as its own class so tests can swap in a fake with the same methods.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote


class GitHubError(RuntimeError):
    """GitHub rejected a call, or could not be reached at all.

    `status` is the HTTP status, or None when nothing was ever answered.
    """

    def __init__(self, status: int | None, message: str):
        self.status = status
        prefix = f"GitHub API error {status}" if status else "GitHub unreachable"
        super().__init__(f"{prefix}: {message}")


class GitHubClient:
    def __init__(self, token: str, api_url: str = "https://api.github.com"):
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        """The decoded response body, or None when there is none.

        (!!) Every error status raises, 404 included. A 404 means "no such
        file" when reading one and "the write did not happen" on any call of
        a commit, and only the caller knows which, so the distinction is not
        made here.

        Failing to reach GitHub raises the same error, without a status, so a
        caller has one exception to handle rather than two. 30 seconds is the
        longest a submission can hang on this.
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

    def get_file(self, owner: str, repo: str, path: str) -> dict[str, Any] | None:
        """The file's contents entry ({sha, content base64, ...}), or None.

        The one place a 404 reads as an absence. GitHub answers 404 for a
        repository the token cannot see too, so None means "not there, or not
        visible with this token".
        """
        try:
            return self._request("GET", f"/repos/{owner}/{repo}/contents/{path}")
        except GitHubError as e:
            if e.status == 404:
                return None
            raise

    def branch_head(self, owner: str, repo: str, branch: str) -> str | None:
        """The commit a branch points at, or None when there is no such
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
        """Commit several files onto `branch`, over `parent`, and return the
        new commit's sha. Creates the branch when it is not there.

        Four calls of the Git Data API, and only the last one writes: the
        parent commit is read for its tree, a tree is built over it, a commit
        is built over that tree, and the branch reference is created or moved
        onto it. The files therefore all land or none does, where one call per
        file leaves a submission half written when the second fails.

        `content` goes into the tree as text, so every file here must be
        UTF-8.

        (!!) The reference is moved without `force`. A branch that moved
        between the read of its head and this move makes GitHub refuse, which
        is the wanted answer: two submissions racing, the second one\'s parent
        is stale, and the write did not happen rather than silently replacing
        what the first one wrote.
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
