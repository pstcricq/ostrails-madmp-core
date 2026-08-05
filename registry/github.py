"""A thin GitHub Contents API client: the two calls this repository needs.

Read one file, write one file, in a repository nobody clones — so the size of
the registry never has to matter here. Standard library only and synchronous,
and worth keeping that way: registering a project is a handful of calls, not
traffic.

The transport ends at this module. It hands out and takes in **bytes**; the
base64 the API speaks, the sha an update must name and the status codes are
its business alone, so nothing above has to know how GitHub stores a file.

**The submission webhook carries its own copy of this**, deployed next to DSW.
The two sides share the registry *layout*, not this code, so a change here
reaches the webhook only if someone carries it over. The registry's README is
the contract they both honour.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class GitHubError(RuntimeError):
    """GitHub rejected a call the caller cannot recover from."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"GitHub API error {status}: {message}")


@dataclass(frozen=True)
class File:
    """One file as it stands on GitHub: what it says, and the version an
    update has to name to replace it rather than clobber it."""

    sha: str
    content: bytes


class GitHubClient:
    def __init__(self, token: str, api_url: str = "https://api.github.com"):
        self.token = token
        self.api_url = api_url.rstrip("/")

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
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
                return response.status, json.loads(payload) if payload else None
        except urllib.error.HTTPError as e:
            # A 404 is only ever "no such file yet", and only on a read: every
            # caller of get_file handles that. On a write it means the
            # repository, or the token's access to it, is wrong — GitHub
            # answers 404 rather than 403 so as not to confirm that a private
            # repository exists — and it must never pass for success.
            if e.code == 404 and method == "GET":
                return 404, None
            raise GitHubError(e.code, e.read().decode()) from e

    def get_file(self, owner: str, repo: str, path: str) -> File | None:
        """The file, or ``None`` when there is none there yet."""
        status, data = self._request("GET", f"/repos/{owner}/{repo}/contents/{path}")
        if status == 404:
            return None
        # Past a megabyte the API stops inlining the content and answers with
        # an empty string and `"encoding": "none"`. Nothing this repository
        # writes comes close, but decoding that would hand back an empty file
        # as if it were the truth — the one failure worth a guard.
        if data.get("encoding") != "base64":
            raise GitHubError(
                200, f"{path}: content not inlined (encoding {data.get('encoding')!r})"
            )
        return File(sha=data["sha"], content=base64.b64decode(data["content"]))

    def put_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: bytes,
        message: str,
        sha: str | None = None,
    ) -> None:
        """Create the file, or replace the version ``sha`` names."""
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content).decode(),
        }
        if sha:
            body["sha"] = sha
        self._request("PUT", f"/repos/{owner}/{repo}/contents/{path}", body)
