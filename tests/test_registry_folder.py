"""What a project's folder in the registry must say, and what converging on it
is allowed to touch.

The registry is a private repository reached over HTTP, so these tests stand a
fake in its place: an in-memory tree of paths to bytes, which records every
write. That is what makes "nothing is sent when nothing changed" a testable
claim rather than a good intention — the assertion is on `fake.writes`.
"""

from pathlib import Path

import pytest
import yaml

from registry import (
    RegistryError,
    converge,
    folder_status,
    meta_document,
    token_from_env,
)
from registry.folder import SUBDIRS, meta_bytes, meta_path
from registry.github import File

ROOT = Path(__file__).parent.parent
GLIDER_CONFIG = ROOT / "configs" / "projects" / "glider.yaml"

CONFIG = {"id": "glider", "rules": [{"rda_dcs": "1.0.0"}, {"ostrails": "1.0.0"}]}
META = "projects/glider/meta.yaml"
KEEPS = [f"projects/glider/{sub}/.gitkeep" for sub in SUBDIRS]


class FakeGitHub:
    """The registry as a dict of path -> bytes, remembering what was written.

    It answers `None` for an unknown path exactly as the real client does on a
    404, which is the only behaviour of the transport this module depends on.
    """

    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})
        self.writes: list[str] = []

    def get_file(self, owner: str, repo: str, path: str) -> File | None:
        if path not in self.files:
            return None
        return File(sha=f"sha-of-{path}", content=self.files[path])

    def put_file(self, owner, repo, path, content, message, sha=None) -> None:
        self.files[path] = content
        self.writes.append(path)


def registry_with(document: dict, keeps: bool = True) -> FakeGitHub:
    """A registry where glider is already registered, saying `document`."""
    files = {META: meta_bytes(document)}
    if keeps:
        files.update(dict.fromkeys(KEEPS, b""))
    return FakeGitHub(files)


def document_in(fake: FakeGitHub) -> dict:
    return yaml.safe_load(fake.files[META])


# What meta.yaml says


def test_meta_holds_the_identity_and_the_pins():
    """The whole file, and the reason it exists: who the project is, and the
    rules versions it was built from, frozen at registration."""
    assert meta_document(CONFIG) == {
        "id": "glider",
        "rules": [{"rda_dcs": "1.0.0"}, {"ostrails": "1.0.0"}],
    }


def test_the_real_config_registers():
    """The tie to the real data: what would be written for the one project
    that exists, read from its config file rather than a fixture."""
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    assert meta_document(config) == {"id": "glider", "rules": config["rules"]}


def test_a_declared_field_no_one_here_reads_stays_out():
    """`name` is in every config and in none of these files. A registry that
    carried it would have to be updated when prose changes — and would invite
    a reader to trust a copy instead of the config."""
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    assert "name" in config
    assert "name" not in meta_document(config)


# The keys that are not ours


def test_a_foreign_key_is_carried_across():
    """A quality-control verdict is written by the registry's own CI. Nothing
    here may erase it — the failure would be silent, and noticed only by
    whoever went looking for a verdict that used to be there."""
    previous = {"id": "glider", "rules": [], "qc": {"status": "pass"}}
    assert meta_document(CONFIG, previous)["qc"] == {"status": "pass"}


def test_a_foreign_key_does_not_make_a_folder_stale():
    """Ours are the only keys compared. Otherwise the first verdict written
    would read as drift, and every sync would fight the registry's CI for the
    file."""
    fake = registry_with({"id": "glider", "rules": CONFIG["rules"], "qc": {}})
    assert folder_status(fake, CONFIG).state == "registered"
    assert converge(fake, CONFIG) == "unchanged"
    assert fake.writes == []


# Missing


def test_a_missing_folder_is_not_a_fault():
    """Adding a project is a config first and a registration second, so the
    push that adds one must not fail the check that has not run yet."""
    status = folder_status(FakeGitHub(), CONFIG)
    assert (status.state, status.is_fault) == ("missing", False)


def test_creating_lays_out_the_whole_folder():
    """`meta.yaml` and both directories, because laying out the folder is
    ours: the webhook writes a document into it and creates nothing."""
    fake = FakeGitHub()
    assert converge(fake, CONFIG) == "created"
    assert fake.writes == [META, *KEEPS]
    assert document_in(fake) == meta_document(CONFIG)


# Registered, and stale


def test_an_up_to_date_folder_is_left_alone():
    """The claim the sync job rests on: it runs on every push to the default
    branch, so a push that changed no config must send nothing at all."""
    fake = registry_with(meta_document(CONFIG))
    assert folder_status(fake, CONFIG).state == "registered"
    assert converge(fake, CONFIG) == "unchanged"
    assert fake.writes == []


def test_a_bumped_pin_makes_the_folder_stale():
    """The drift the whole package exists to prevent: the config pins one
    version, the registry still names another."""
    fake = registry_with({"id": "glider", "rules": [{"rda_dcs": "0.9.0"}]})
    assert folder_status(fake, CONFIG).state == "stale"
    assert converge(fake, CONFIG) == "updated"
    assert fake.writes == [META]
    assert document_in(fake)["rules"] == CONFIG["rules"]


def test_a_missing_subdir_is_created_without_touching_meta():
    """The two writes are independent: a folder whose meta.yaml is right but
    whose directories were removed gets them back, and nothing else."""
    fake = registry_with(meta_document(CONFIG), keeps=False)
    assert converge(fake, CONFIG) == "unchanged"
    assert fake.writes == KEEPS


def test_key_order_alone_is_not_a_change():
    """What decides is the document, not the bytes. A file that says the right
    thing in another order is already right, and rewriting it would be a commit
    nobody can read a difference in."""
    fake = registry_with({"rules": CONFIG["rules"], "id": "glider"})
    assert folder_status(fake, CONFIG).state == "registered"
    assert converge(fake, CONFIG) == "unchanged"
    assert fake.writes == []


# Collision


def test_another_projects_folder_is_a_fault():
    """The one state syncing cannot fix, and the only one this reports as a
    fault: two projects cannot both be right about one destination."""
    fake = registry_with({"id": "canales", "rules": []})
    status = folder_status(fake, CONFIG)
    assert (status.state, status.is_fault) == ("collision", True)
    assert "canales" in status.detail and "glider" in status.detail


def test_converging_refuses_to_clobber_another_project():
    """Refusing is the point: that folder is where somebody else's DMPs land."""
    fake = registry_with({"id": "canales", "rules": []})
    with pytest.raises(RegistryError) as caught:
        converge(fake, CONFIG)
    assert fake.writes == []
    assert "projects/glider" in str(caught.value)
    assert "'canales'" in str(caught.value)


# Where a project's folder is, and what opens it


def test_the_folder_is_named_after_the_id():
    """One string names the config file, the registry folder and the DSW
    packages. There is nothing here to keep in step with anything."""
    assert meta_path(CONFIG) == META


def test_the_token_has_one_name():
    """`REGISTRY_TOKEN` is what the whole deployment uses — the submission
    webhook reads the same one."""
    with pytest.MonkeyPatch.context() as env:
        env.setenv("REGISTRY_TOKEN", "t")
        assert token_from_env() == "t"


def test_a_workflows_own_token_is_not_a_fallback():
    """A workflow's default token is scoped to the repository running it, not
    to the registry, and a token without access reads as 404 — which the
    client turns into "no file yet". Falling back would report a project
    missing when the truth is a wrong token: green, and wrong, exactly where
    there is no write to catch it."""
    with pytest.MonkeyPatch.context() as env:
        env.delenv("REGISTRY_TOKEN", raising=False)
        env.setenv("GITHUB_TOKEN", "would-not-work")
        assert token_from_env() == ""
