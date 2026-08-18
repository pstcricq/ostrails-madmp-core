"""The transport, and the one status code it reads as an answer rather than an
error.

These tests stand a fake `urlopen` in place of the network. What they are
about is the asymmetry: a 404 means "no such file yet" on a read, and means a
wrong repository or a wrong token on a write, where taking it for success
would report a project registered that is not there.
"""

import base64
import io
import json
import urllib.error

import pytest

from registry.github import GitHubClient, GitHubError

CALL = "https://api.github.com/repos/o/r/contents/projects/glider/template/.gitkeep"
PATH = "projects/glider/template/.gitkeep"


class FakeResponse:
    def __init__(self, status: int, payload: bytes):
        self.status = status
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
        return FakeResponse(200, b"" if body is None else json.dumps(body).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
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


def test_a_file_comes_back_as_bytes_and_a_sha(monkeypatch):
    """The transport ends here, base64 is its business, and what it hands
    out is what the file says, plus the version an update has to name."""
    client = answering(monkeypatch, body=contents(b"id: glider\n"))
    file = client.get_file("o", "r", PATH)
    assert (file.sha, file.content) == ("abc", b"id: glider\n")


def test_a_missing_file_reads_as_nothing_there(monkeypatch):
    """404 on a GET is the answer every caller of get_file handles."""
    client = answering(monkeypatch, error=http_error(404))
    assert client.get_file("o", "r", PATH) is None


def test_any_other_failure_on_a_read_still_raises(monkeypatch):
    """Only 404 is an answer. A 500 read as "no file yet" would have the sync
    create a folder that already exists."""
    client = answering(monkeypatch, error=http_error(500))
    with pytest.raises(GitHubError) as caught:
        client.get_file("o", "r", PATH)
    assert caught.value.status == 500


def test_content_the_api_did_not_inline_is_refused(monkeypatch):
    """Past a megabyte the API answers with an empty string and no base64
    encoding. Decoding that would hand back an empty file as if it were the
    truth."""
    client = answering(
        monkeypatch, body={"sha": "abc", "encoding": "none", "content": ""}
    )
    with pytest.raises(GitHubError, match="not inlined"):
        client.get_file("o", "r", PATH)


# Writing


def test_a_write_sends_the_bytes_and_names_the_version_it_replaces(monkeypatch):
    requests = []
    client = answering(monkeypatch, record=requests)
    client.put_file("o", "r", PATH, b"id: glider\n", "register", sha="abc")
    body = json.loads(requests[0].data)
    assert requests[0].method == "PUT"
    assert base64.b64decode(body["content"]) == b"id: glider\n"
    assert (body["message"], body["sha"]) == ("register", "abc")


def test_a_creation_names_no_version(monkeypatch):
    """`sha` says "replace this version". Sending one for a file that does not
    exist is how GitHub is told the caller is confused."""
    requests = []
    client = answering(monkeypatch, record=requests)
    client.put_file("o", "r", PATH, b"", "register")
    assert "sha" not in json.loads(requests[0].data)


def test_a_404_on_a_write_is_a_failure(monkeypatch):
    """The asymmetry that matters. GitHub answers 404 rather than 403 so as
    not to confirm a private repository exists, so a wrong token or a wrong
    repository looks exactly like a missing file, and must not pass for
    success."""
    client = answering(monkeypatch, error=http_error(404))
    with pytest.raises(GitHubError) as caught:
        client.put_file("o", "r", PATH, b"", "register")
    assert caught.value.status == 404
