"""The transport, and what it makes of a status code.

These tests stand a fake ``urlopen`` in place of the network, so nothing here
touches GitHub. What they pin down is the asymmetry every caller rests on: a
404 is an answer on a read, "there is no such file", and a failure on a write,
where taking it for success would report something written that is not there.
"""

import base64
import io
import json
import urllib.error
import urllib.request

import pytest

from utils.github import GitHubClient, GitHubError

CALL = "https://api.github.com/repos/o/r/contents/projects/glider/template/.gitkeep"
PATH = "projects/glider/template/.gitkeep"


class FakeResponse:
    """Shaped like urlopen's return value: a context manager that reads once."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def answering(monkeypatch, body=None, error=None, record=None) -> GitHubClient:
    """Point a client at a canned answer, recording the request it made."""

    def fake_urlopen(request, timeout=None):
        if record is not None:
            record.append(request)
        if error is not None:
            raise error
        return FakeResponse(b"" if body is None else json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return GitHubClient(token="t")


def http_error(code: int, body: bytes = b"nope") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(CALL, code, "msg", {}, io.BytesIO(body))


def contents(text: bytes) -> dict:
    return {
        "sha": "abc",
        "encoding": "base64",
        "content": base64.b64encode(text).decode(),
    }


# Reading


def test_a_file_comes_back_as_bytes(monkeypatch):
    """The transport ends here, base64 is its business, and what it hands out
    is what the file says."""
    client = answering(monkeypatch, body=contents(b"id: glider\n"))
    assert client.get_file("o", "r", PATH) == b"id: glider\n"


def test_a_missing_file_reads_as_nothing_there(monkeypatch):
    """404 on a read is the answer every caller of get_file handles."""
    client = answering(monkeypatch, error=http_error(404))
    assert client.get_file("o", "r", PATH) is None


def test_any_other_failure_on_a_read_still_raises(monkeypatch):
    """Only 404 is an answer. A 500 read as "no file yet" would report a file
    absent that is very likely there."""
    client = answering(monkeypatch, error=http_error(500))
    with pytest.raises(GitHubError) as caught:
        client.get_file("o", "r", PATH)
    assert caught.value.status == 500


def test_content_the_api_did_not_inline_is_refused(monkeypatch):
    """Past a megabyte the API answers with an empty string and no base64
    encoding. Decoding that would hand back an empty file as if it were the
    truth, and a caller comparing what it holds would never find it equal."""
    client = answering(
        monkeypatch, body={"sha": "abc", "encoding": "none", "content": ""}
    )
    with pytest.raises(GitHubError, match="not inlined"):
        client.get_file("o", "r", PATH)


# Writing one file


def test_a_write_sends_the_bytes_and_names_no_version(monkeypatch):
    """A creation. GitHub takes a `sha` to mean "replace that version", and
    sending none is what makes it refuse rather than overwrite a file that is
    already there."""
    requests = []
    client = answering(monkeypatch, record=requests)
    client.create_file("o", "r", PATH, b"id: glider\n", "register")
    body = json.loads(requests[0].data)
    assert requests[0].method == "PUT"
    assert base64.b64decode(body["content"]) == b"id: glider\n"
    assert body["message"] == "register"
    assert "sha" not in body


def test_a_404_on_a_write_is_a_failure(monkeypatch):
    """The asymmetry that matters. GitHub answers 404 rather than 403 so as
    not to confirm a private repository exists, so a wrong token or a wrong
    repository looks exactly like a missing file, and must not pass for
    success."""
    client = answering(monkeypatch, error=http_error(404))
    with pytest.raises(GitHubError) as caught:
        client.create_file("o", "r", PATH, b"", "register")
    assert caught.value.status == 404


# Branches and commits


def test_an_absent_branch_is_absent_and_not_an_error(monkeypatch):
    """A repository whose branch cannot be read is one nothing can be
    committed to, and the caller has to be able to tell that from a refusal."""
    client = answering(monkeypatch, error=http_error(404))
    assert client.branch_head("o", "r", "main") is None


def test_a_commit_treats_a_404_as_a_failure(monkeypatch):
    """A 404 on a write means the write did not happen. Read as an absence,
    the way a read does, it would let a caller that wrote nothing report a
    file it could link to."""
    client = answering(monkeypatch, error=http_error(404))
    with pytest.raises(GitHubError) as caught:
        client.commit_files("o", "r", "main", {"p": b"x"}, "message", "parent")
    assert caught.value.status == 404


def _stub_git_data(monkeypatch):
    """A GitHub that answers the four calls a commit makes, and hands back
    every request that was built, in order."""
    seen: list[urllib.request.Request] = []
    answers = {
        "/git/commits/parent": {"tree": {"sha": "base"}},
        "/git/trees": {"sha": "new-tree"},
        "/git/commits": {"sha": "new-commit"},
        "/git/refs/heads/main": {},
    }

    def stub(request, timeout=None):
        seen.append(request)
        for suffix, payload in answers.items():
            if request.full_url.endswith(suffix):
                return FakeResponse(json.dumps(payload).encode())
        raise AssertionError(f"unexpected call {request.full_url}")

    monkeypatch.setattr(urllib.request, "urlopen", stub)
    return seen


def test_a_commit_builds_a_tree_then_moves_the_branch(monkeypatch):
    """The order is what makes the write atomic: the files go into a tree and
    a commit, neither of which anything points at, and one reference move
    publishes them all at once."""
    seen = _stub_git_data(monkeypatch)
    sha = GitHubClient("token").commit_files(
        "o", "r", "main", {"a/one.json": b"1", "a/two.json": b"2"}, "msg", "parent"
    )
    assert sha == "new-commit"
    assert [r.get_method() for r in seen] == ["GET", "POST", "POST", "PATCH"]
    assert [r.full_url.split("/repos/o/r")[1] for r in seen] == [
        "/git/commits/parent",
        "/git/trees",
        "/git/commits",
        "/git/refs/heads/main",
    ]
    tree = json.loads(seen[1].data)
    assert tree["base_tree"] == "base"
    assert {entry["path"]: entry["content"] for entry in tree["tree"]} == {
        "a/one.json": "1",
        "a/two.json": "2",
    }
    assert all(entry["mode"] == "100644" for entry in tree["tree"])
    commit = json.loads(seen[2].data)
    assert (commit["tree"], commit["parents"], commit["message"]) == (
        "new-tree",
        ["parent"],
        "msg",
    )
    moved = json.loads(seen[3].data)
    # Not forced: a branch that moved between the read of its head and this
    # move makes GitHub refuse, and the write does not happen.
    assert moved == {"sha": "new-commit"}
    assert seen[0].headers["Authorization"] == "Bearer token"


# Reaching GitHub at all


def test_unreachable_github_is_the_same_error_without_a_status(monkeypatch):
    """DNS down, connection refused, timeout: never a response, so no status.
    Same exception as a refusal, so a caller has one type to catch instead of
    an OSError on top of it."""
    client = answering(
        monkeypatch, error=urllib.error.URLError("nodename nor servname provided")
    )
    with pytest.raises(GitHubError) as caught:
        client.get_file("o", "r", PATH)
    assert caught.value.status is None
    assert "unreachable" in str(caught.value)
