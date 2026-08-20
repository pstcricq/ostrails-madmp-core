"""The submission webhook, in seven sections.

Routing, the provenance block, idempotence, the check and the guards drive
service.py through FakeGitHub. The HTTP layer goes through TestClient.
Configuration covers what app.py reads at startup.

Nothing here touches the transport, FakeGitHub stands in for it throughout."""

import json

import pytest
from fastapi.testclient import TestClient

from quality_control import STATUSES
from submission.app import Settings, _from_environment, app
from submission.service import (
    _SPELLED_OUT,
    QualityControlError,
    SubmissionConfig,
    SubmissionError,
    handle_submission,
)
from utils.github import GitHubError

CONFIG = SubmissionConfig(github_owner="Pierrott64", registry_repo="dmp-registry")
DSW_URL = "http://localhost:8080/wizard/projects/7c42caa4-a0e0-4112-9623-4334641c457a"
DMP_PATH = "projects/glider/template/dmp_glider_template.json"
META_PATH = "projects/glider/template/dmp_glider_template.meta.json"
CHECK_PATH = "projects/glider/template/dmp_glider_template.check.json"
RAW_URL = f"https://raw.githubusercontent.com/Pierrott64/dmp-registry/main/{DMP_PATH}"
PROVENANCE = {
    "project": "glider",
    "template_version": "1.0.0",
    "rules": [{"rda_dcs": "1.0.0"}, {"ostrails": "1.0.0"}],
}


# A DMP answering everything the pinned rules require. The webhook checks a
# document before it offers it, so anything less is refused before the routing
# these tests are about is ever reached.
COMPLETE = {
    "title": "Glider mission DMP",
    "language": "eng",
    "created": "2026-08-18T09:00:00Z",
    "modified": "2026-08-18T09:00:00Z",
    "ethical_issues_exist": "no",
    "dmp_id": {"identifier": DSW_URL, "type": "url"},
    "contact": {
        "name": "Albert Einstein",
        "mbox": "albert@example.com",
        "contact_id": [{"identifier": "0000-0001-2345-6789", "type": "orcid"}],
    },
    "dataset": [
        {
            "title": "CTD",
            "personal_data": "no",
            "sensitive_data": "no",
            "dataset_id": {"identifier": "https://doi.org/10.5281/x", "type": "doi"},
        }
    ],
}


def _document(
    title="Glider mission DMP", identifier=DSW_URL, provenance=None, dmp=None
):
    """What a maDMP document template renders: the dmp object, and beside it
    the provenance block the webhook takes back out."""
    document = {"dmp": json.loads(json.dumps(COMPLETE if dmp is None else dmp))}
    if dmp is None:
        document["dmp"]["title"] = title
        document["dmp"]["dmp_id"] = {"identifier": identifier, "type": "url"}
    provenance = PROVENANCE if provenance is None else provenance
    if provenance is not ...:
        document["metadata"] = json.loads(json.dumps(provenance))
    return document


class FakeGitHub:
    """In-memory stand-in for the client: the registry as path -> bytes,
    plus the commit its default branch points at.

    A commit is recorded as the paths it carried and its message, so a test
    can assert that several files travelled together. Its parent is checked
    against the head that was handed out, which is what makes "the write did
    not happen when the branch moved" a claim these tests can rest on.
    """

    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})
        self.commits: list[tuple[list[str], str]] = []
        self.head = "sha0"

    def get_file(self, owner, repo, path):
        return self.files.get(path)

    def branch_head(self, owner, repo, branch):
        return self.head

    def commit_files(self, owner, repo, branch, files, message, parent):
        assert parent == self.head, "committed over a parent that is not the head"
        self.files.update(files)
        self.head = f"sha{len(self.commits) + 1}"
        self.commits.append((sorted(files), message))
        return self.head


def _initialized(folder="glider") -> FakeGitHub:
    """A registry where the project's folder has already been laid out."""
    return FakeGitHub({f"projects/{folder}/template/.gitkeep": b""})


# Routing + dmp_id rewrite


def test_first_submit_writes_the_dmp_and_rewrites_dmp_id():
    github = _initialized("glider")
    result = handle_submission(_document(), "glider", github, CONFIG)
    assert result["action"] == "created"
    assert result["file"] == DMP_PATH
    stored = json.loads(github.files[DMP_PATH])
    # dmp_id was the DSW placeholder, the webhook rewrote it to the registry URL.
    assert stored["dmp"]["dmp_id"] == {"identifier": RAW_URL, "type": "url"}
    assert stored["dmp"]["title"] == "Glider mission DMP"


def test_folder_only_touches_its_own_path():
    github = _initialized("glider")
    handle_submission(_document(), "glider", github, CONFIG)
    assert [paths for paths, _ in github.commits] == [[CHECK_PATH, DMP_PATH, META_PATH]]


def test_commit_message_names_the_project():
    """Every project commits into the same repository, so ``git log`` needs the
    folder in the message to be readable at all."""
    github = _initialized("glider")
    handle_submission(_document(), "glider", github, CONFIG)
    handle_submission(_document(title="Renamed"), "glider", github, CONFIG)
    assert [message for _, message in github.commits] == [
        "Add DMP for glider (DSW submission)",
        "Update DMP for glider (DSW submission)",
    ]


# The provenance block


def test_the_provenance_leaves_the_dmp_and_lands_beside_it():
    """The whole point of the block: what the registry holds is RDA DCS and
    nothing else, and the versions it was built from sit next to it, written
    by the same commit so the two can never disagree."""
    github = _initialized()
    result = handle_submission(_document(), "glider", github, CONFIG)
    assert result["metadata"] == META_PATH
    assert "metadata" not in json.loads(github.files[DMP_PATH])
    assert json.loads(github.files[META_PATH]) == PROVENANCE


def test_the_provenance_travels_in_the_commit_that_carries_the_dmp():
    """One commit, both files. Two commits would let the second fail and
    leave a DMP whose rules versions nobody knows."""
    github = _initialized()
    handle_submission(_document(), "glider", github, CONFIG)
    assert len(github.commits) == 1
    assert github.commits[0][0] == [CHECK_PATH, DMP_PATH, META_PATH]


def test_a_document_without_provenance_is_refused():
    """A DMP whose rules versions are unknown cannot be checked against them,
    and a folder holding one would have to be cleaned up by hand."""
    github = _initialized()
    with pytest.raises(SubmissionError, match="carries no 'metadata' object"):
        handle_submission(_document(provenance=...), "glider", github, CONFIG)
    assert github.commits == []


def test_provenance_naming_another_project_is_refused():
    """The folder comes from the service URL and the project name from the
    template. They disagreeing means the document was submitted through
    somebody else's service, and it must not land in that folder."""
    provenance = {**PROVENANCE, "project": "canales"}
    with pytest.raises(SubmissionError, match="generated for project 'canales'"):
        handle_submission(
            _document(provenance=provenance), "glider", _initialized(), CONFIG
        )


@pytest.mark.parametrize(
    "rules",
    [
        pytest.param(None, id="absent"),
        pytest.param([], id="empty"),
        pytest.param("rda_dcs 1.0.0", id="a string"),
        pytest.param([{"rda_dcs": "1.0.0", "ostrails": "1.0.0"}], id="two keys in one"),
        pytest.param([{"rda_dcs": 1.0}], id="an unquoted version"),
        pytest.param([{"rda_dcs": ""}], id="an empty version"),
    ],
)
def test_malformed_pins_are_refused(rules):
    """Quality control resolves these into file paths, so a shape it cannot
    read has to be caught here, while there is still somebody to tell."""
    provenance = {**PROVENANCE, "rules": rules}
    github = _initialized()
    with pytest.raises(SubmissionError, match="metadata.rules"):
        handle_submission(_document(provenance=provenance), "glider", github, CONFIG)
    assert github.commits == []


# Idempotence


def test_resubmit_same_content_commits_nothing():
    github = _initialized()
    handle_submission(_document(), "glider", github, CONFIG)
    before = list(github.commits)
    result = handle_submission(_document(), "glider", github, CONFIG)
    assert result["action"] == "unchanged"
    assert github.commits == before


def test_resubmit_of_an_already_rewritten_document_is_unchanged():
    """The second submission of the same DMP arrives with dmp_id already
    pointing at the registry, since that is what the first one wrote back.
    Rewriting it to the same value has to leave the content identical."""
    github = _initialized()
    handle_submission(_document(), "glider", github, CONFIG)
    result = handle_submission(_document(identifier=RAW_URL), "glider", github, CONFIG)
    assert result["action"] == "unchanged"


def test_resubmit_changed_content_updates():
    github = _initialized()
    handle_submission(_document(), "glider", github, CONFIG)
    before = len(github.commits)
    result = handle_submission(
        _document(title="Renamed project"), "glider", github, CONFIG
    )
    assert result["action"] == "updated"
    assert [paths for paths, _ in github.commits[before:]] == [
        [CHECK_PATH, DMP_PATH, META_PATH]
    ]


def test_a_new_template_version_alone_is_an_update():
    """The provenance block is compared like the DMP is. A researcher who answered
    nothing new but migrated to a newer template has to leave a trace, that
    is the fact quality control reads."""
    github = _initialized()
    handle_submission(_document(), "glider", github, CONFIG)
    provenance = {**PROVENANCE, "template_version": "2.0.0"}
    result = handle_submission(
        _document(provenance=provenance), "glider", github, CONFIG
    )
    assert result["action"] == "updated"
    assert json.loads(github.files[META_PATH])["template_version"] == "2.0.0"


# The check the document has to pass


def test_the_verdict_lands_beside_the_dmp():
    """The registry holds what passed, and says so: what judged it, against
    which versions, and what it still had to remark. Without this a document
    in the registry is a document nobody can tell was checked."""
    github = _initialized()
    result = handle_submission(_document(), "glider", github, CONFIG)
    assert result["check"] == CHECK_PATH
    written = json.loads(github.files[CHECK_PATH])
    assert written["verdict"] == "pass"
    assert written["rules_versions"] == {"rda_dcs": "1.0.0", "ostrails": "1.0.0"}
    assert written["dmp"] == DMP_PATH
    assert written["engine"]
    assert written["summary"]["fail"] == 0


def test_the_verdict_is_the_shape_the_command_writes():
    """One shape for both, so anything reading a check reads one thing. The
    four lists and their counts are the whole of it, and a reader shows them
    by severity without filtering."""
    loose = json.loads(json.dumps(COMPLETE))
    loose["contact"]["contact_id"][0]["type"] = "something else"
    github = _initialized()
    handle_submission(_document(dmp=loose), "glider", github, CONFIG)
    written = json.loads(github.files[CHECK_PATH])
    for status in STATUSES:
        assert len(written[status]) == written["summary"][status], status
    assert written["warning"]
    assert "contact_id" in written["warning"][0]["instance_path"]
    # Structurally empty here, a document that fails never reaches the
    # registry at all, and the key is there so a reader needs no special case.
    assert written["fail"] == []


def test_the_verdict_carries_no_timestamp():
    """One would change the bytes at every submission, so an unchanged DMP
    would commit again for ever."""
    github = _initialized()
    handle_submission(_document(), "glider", github, CONFIG)
    first = github.files[CHECK_PATH]
    result = handle_submission(_document(), "glider", github, CONFIG)
    assert result["action"] == "unchanged"
    assert github.files[CHECK_PATH] == first


def test_a_document_that_does_not_hold_up_is_refused():
    """Refused before anything is read or written, so a DMP with holes never
    reaches the registry and the researcher hears why in DSW."""
    github = _initialized()
    incomplete = {k: v for k, v in COMPLETE.items() if k != "language"}
    with pytest.raises(QualityControlError, match="Quality control failed"):
        handle_submission(_document(dmp=incomplete), "glider", github, CONFIG)
    assert github.commits == []


def test_a_refusal_names_what_to_fix_and_what_judged_it():
    """The message is the whole of what the researcher gets, so it says which
    fields and against which versions."""
    incomplete = {k: v for k, v in COMPLETE.items() if k != "language"}
    with pytest.raises(QualityControlError) as raised:
        handle_submission(_document(dmp=incomplete), "glider", _initialized(), CONFIG)
    message = str(raised.value)
    assert "dmp.language" in message
    assert "rda_dcs 1.0.0" in message and "ostrails 1.0.0" in message


def test_a_refusal_spells_out_only_the_first_few():
    """DSW shows this on the submission, not a report. A document missing
    everything must not push the beginning of the message out of sight."""
    many = {"dataset": [{} for _ in range(5)]}
    with pytest.raises(QualityControlError) as raised:
        handle_submission(_document(dmp=many), "glider", _initialized(), CONFIG)
    message = str(raised.value)
    listed = [line for line in message.splitlines() if line.startswith("  ")]
    assert len(listed) == _SPELLED_OUT + 1  # the cut is one of them
    assert listed[-1] == "  [...] 7 more not shown."


def test_a_truncated_refusal_still_names_the_whole_count():
    """The list is cut, the number never is, or a researcher fixes twenty and
    submits again believing they are done."""
    many = {"dataset": [{} for _ in range(5)]}
    with pytest.raises(QualityControlError) as raised:
        handle_submission(_document(dmp=many), "glider", _initialized(), CONFIG)
    assert "27 violation(s) to fix, the first 20:" in str(raised.value)


def test_a_short_refusal_announces_no_cut():
    """Under the cap there is nothing to warn about, and saying "the first 20"
    of eight would read as if something were hidden."""
    with pytest.raises(QualityControlError) as raised:
        handle_submission(_document(dmp={}), "glider", _initialized(), CONFIG)
    message = str(raised.value)
    assert "8 violation(s) to fix:" in message
    assert "not shown" not in message


def test_a_refusal_separates_the_warnings_from_what_it_refuses_for():
    """A warning never blocks, so a message that lists it beside the
    violations would have the researcher chasing something that is not the
    reason."""
    loose = {k: v for k, v in COMPLETE.items() if k != "language"}
    loose = json.loads(json.dumps(loose))
    loose["contact"]["contact_id"][0]["type"] = "something else"
    with pytest.raises(QualityControlError) as raised:
        handle_submission(_document(dmp=loose), "glider", _initialized(), CONFIG)
    message = str(raised.value)
    assert "which do not block" in message
    assert message.index("violation(s) to fix") < message.index("warning(s)")


def test_a_refusal_ends_on_what_did_hold_up():
    """The scale of what is wrong, against the scale of the document."""
    with pytest.raises(QualityControlError) as raised:
        handle_submission(_document(dmp={}), "glider", _initialized(), CONFIG)
    assert str(raised.value).splitlines()[-1].endswith("optional fields left empty.")


def test_a_warning_alone_does_not_refuse():
    """Suggestions do not gate here either, or every free-text answer would
    stop a submission."""
    loose = json.loads(json.dumps(COMPLETE))
    loose["contact"]["contact_id"][0]["type"] = "something else"
    result = handle_submission(_document(dmp=loose), "glider", _initialized(), CONFIG)
    assert result["action"] == "created"


def test_pins_naming_rules_nobody_wrote_are_refused():
    """The provenance block is well formed and names a version that does not exist.
    Nothing can judge the document, so it is not offered."""
    provenance = {**PROVENANCE, "rules": [{"rda_dcs": "9.9.9"}]}
    github = _initialized()
    with pytest.raises(QualityControlError, match="cannot be loaded"):
        handle_submission(_document(provenance=provenance), "glider", github, CONFIG)
    assert github.commits == []


def test_a_submitted_document_carries_a_message_of_its_own():
    """(!!) DSW shows none of this, its client reads the body only on a
    failure. Carried anyway, so anything else reading a submission has it."""
    github = _initialized()
    result = handle_submission(_document(), "glider", github, CONFIG)
    assert result["message"].startswith("Submitted.")
    assert "checks passed" in result["message"]


def test_a_submission_with_warnings_says_so_in_its_message():
    loose = json.loads(json.dumps(COMPLETE))
    loose["contact"]["contact_id"][0]["type"] = "something else"
    result = handle_submission(_document(dmp=loose), "glider", _initialized(), CONFIG)
    assert "Submitted with 1 warning(s):" in result["message"]
    assert "contact_id" in result["message"]


# Guards


def test_uninitialized_folder_refused():
    """No template/.gitkeep (the project was never registered) -> refuse,
    don't half-create."""
    github = FakeGitHub()
    with pytest.raises(SubmissionError, match="not initialized"):
        handle_submission(_document(), "glider", github, CONFIG)


@pytest.mark.parametrize("folder", ["", "../evil", "a/b", "UPPER", "dot.dot", "sp ace"])
def test_unsafe_folder_refused(folder):
    with pytest.raises(SubmissionError, match="invalid project folder"):
        handle_submission(_document(), folder, _initialized(), CONFIG)


def test_document_without_dmp_refused():
    with pytest.raises(SubmissionError, match="no dmp object"):
        handle_submission({"foo": 1}, "glider", _initialized(), CONFIG)


# HTTP layer


@pytest.fixture()
def client(monkeypatch):
    """``app`` is a module-level singleton, so its one seam is installed through
    monkeypatch, which puts the real builder back after every test."""
    settings = Settings(
        submission_token="s3cret", github=_initialized("glider"), config=CONFIG
    )
    monkeypatch.setattr(app.state, "build", lambda: settings)
    with TestClient(app) as test_client:
        yield test_client


def test_health_answers_when_the_webhook_is_configured(client):
    """The compose healthcheck polls this, so ``up --wait`` and the container's
    restart both hang on it answering."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_needs_no_token(client):
    """It is called by docker, which has no business holding the shared
    secret."""
    assert client.get("/health").status_code == 200


def test_http_rejects_bad_token(client):
    response = client.post(
        "/submissions?project=glider",
        content=json.dumps(_document()),
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_http_rejects_a_non_ascii_token(client):
    """The header is whatever the caller sent, and compare_digest refuses
    non-ASCII strings, so the comparison has to happen on bytes. Anything else
    turns a wrong token into a 500."""
    response = client.post(
        "/submissions?project=glider",
        content=json.dumps(_document()),
        # Raw bytes: httpx refuses to build a non-ASCII header from a str, but
        # nothing stops a client from putting these on the wire, and starlette
        # decodes them as latin-1.
        headers={"Authorization": "Bearer clé".encode("latin-1")},
    )
    assert response.status_code == 401


def test_http_missing_project_is_400(client):
    response = client.post(
        "/submissions",
        content=json.dumps(_document()),
        headers={"Authorization": "Bearer s3cret", "Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_http_raw_json_body(client):
    response = client.post(
        "/submissions?project=glider",
        content=json.dumps(_document()),
        headers={"Authorization": "Bearer s3cret", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["action"] == "created"
    assert response.json()["folder"] == "glider"
    # The one thing the researcher is handed: where their DMP now sits.
    assert response.headers["location"] == response.json()["repository"]


def test_http_multipart_body(client):
    response = client.post(
        "/submissions?project=glider",
        files={"file": ("dmp.json", json.dumps(_document()), "application/json")},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert response.status_code == 200
    assert response.json()["action"] == "created"


def test_http_reports_a_refused_write_rather_than_success(monkeypatch):
    """What a revoked or mis-scoped token looks like: the registry reads fine
    and refuses the write. DSW has to see a failure, not a submission it will
    believe was filed."""

    class RefusingGitHub(FakeGitHub):
        def commit_files(self, *args, **kwargs):
            raise GitHubError(404, "Not Found")

    settings = Settings(
        submission_token="s3cret",
        github=RefusingGitHub({"projects/glider/template/.gitkeep": b""}),
        config=CONFIG,
    )
    monkeypatch.setattr(app.state, "build", lambda: settings)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/submissions?project=glider",
            content=json.dumps(_document()),
            headers={
                "Authorization": "Bearer s3cret",
                "Content-Type": "application/json",
            },
        )
    assert response.status_code == 502


def test_http_bad_json_is_400(client):
    response = client.post(
        "/submissions?project=glider",
        content=b"not json",
        headers={"Authorization": "Bearer s3cret"},
    )
    assert response.status_code == 400


def test_a_refused_submission_answers_in_plain_text(client):
    """(!!) DSW opens the response body raw on a failed submission, so
    FastAPI's ``{"detail": ...}`` would show the researcher the JSON wrapper
    around their own message, on one line."""
    response = client.post(
        "/submissions?project=glider",
        content=json.dumps(_document(dmp={})),
        headers={
            "Authorization": "Bearer s3cret",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/plain")
    assert not response.text.startswith("{")
    assert response.text.startswith("Quality control failed against")
    assert "\n  Required field" in response.text


def test_every_other_refusal_is_plain_text_too(client):
    """One rendering for all of them, they all land in the same DSW window."""
    response = client.post(
        "/submissions",
        content="{}",
        headers={
            "Authorization": "Bearer s3cret",
            "Content-Type": "application/json",
        },
    )
    assert response.status_code == 400
    assert response.text == "missing ?project=<folder> query parameter"


# Configuration read from the environment
#
# Unset and empty are tested alike because compose always defines what its
# ``environment:`` block lists: a value absent from .env reaches the container as
# an empty string, not as a missing variable. Both must fail, and fail the same
# way, or the webhook commits somewhere nobody asked for, or serves with no
# shared secret at all.

ENVIRONMENT = {
    "SUBMISSION_TOKEN": "s3cret",
    "REGISTRY_TOKEN": "ghp_registry",
    "REGISTRY_OWNER": "Pierrott64",
    "REGISTRY_REPO": "dmp-registry",
}


@pytest.fixture()
def environment(monkeypatch):
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


def test_settings_read_the_environment(environment):
    settings = _from_environment()
    assert settings.submission_token == "s3cret"
    assert settings.github.token == "ghp_registry"
    assert settings.config == CONFIG


@pytest.mark.parametrize("missing", list(ENVIRONMENT))
def test_settings_refuse_an_unset_variable(environment, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        _from_environment()


@pytest.mark.parametrize("empty", list(ENVIRONMENT))
def test_settings_refuse_an_empty_variable(environment, monkeypatch, empty):
    monkeypatch.setenv(empty, "")
    with pytest.raises(RuntimeError, match=empty):
        _from_environment()


def test_every_unset_variable_is_named_at_once(monkeypatch):
    """One pass to fix a fresh deployment, not one restart per variable."""
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError) as raised:
        _from_environment()
    assert all(name in str(raised.value) for name in ENVIRONMENT)


def test_startup_refuses_an_incomplete_environment(monkeypatch):
    """The webhook does not serve at all, where reading the environment per
    request would let it answer /health and fail on the first submission."""
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="SUBMISSION_TOKEN"), TestClient(app):
        pass  # pragma: no cover
