"""What a project's folder in the registry is, and what converging on it is
allowed to touch.

The registry is a private repository reached over HTTP, so these tests stand a
fake in its place: an in-memory tree of paths to bytes, which records every
write, so "nothing is sent when nothing changed" is a claim the assertions can
be made on, against ``fake.writes``.
"""

from pathlib import Path

import pytest
import yaml

from registry import (
    Registry,
    RegistryError,
    converge,
    folder_status,
    registry_from_env,
    token_from_env,
)
from registry.folder import SUBDIRS, keep_path

ROOT = Path(__file__).parent.parent
GLIDER_CONFIG = ROOT / "configs" / "projects" / "glider.yaml"

REGISTRY = Registry(owner="o", repo="r")
# ``id`` is the one key this package reads, a real config carries many more.
CONFIG = {"id": "glider"}
KEEPS = [f"projects/glider/{sub}/.gitkeep" for sub in SUBDIRS]


class FakeGitHub:
    """The registry as a dict of path -> bytes, remembering what was written.

    It answers ``None`` for an unknown path exactly as the real client does on a
    404, which is the only behaviour of the transport this module depends on.
    """

    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})
        self.writes: list[str] = []
        self.calls: list[tuple[str, str, str]] = []

    def get_file(self, owner: str, repo: str, path: str) -> bytes | None:
        self.calls.append((owner, repo, path))
        return self.files.get(path)

    def create_file(self, owner, repo, path, content, message) -> None:
        self.calls.append((owner, repo, path))
        self.files[path] = content
        self.writes.append(path)


def registry_with(*subdirs: str) -> FakeGitHub:
    """A registry where these of glider's subdirectories are laid out, and no
    other."""
    return FakeGitHub(dict.fromkeys((keep_path(CONFIG, sub) for sub in subdirs), b""))


# Missing


def test_a_folder_that_is_not_there_yet_is_missing():
    """Adding a project is a config first and a registration second, so the
    push that adds one finds nothing and says so rather than failing."""
    assert folder_status(FakeGitHub(), REGISTRY, CONFIG).state == "missing"


def test_creating_lays_out_both_subdirectories():
    """Laying out the folder is ours: the webhook writes a document into it
    and creates nothing, so a folder half laid out is a Submit that fails."""
    fake = FakeGitHub()
    assert converge(fake, REGISTRY, CONFIG) == "created"
    assert fake.writes == KEEPS


def test_the_real_config_lays_out_the_real_folder():
    """The tie to the real data: where the one project that exists is
    registered, read from its config file rather than a fixture."""
    config = yaml.safe_load(GLIDER_CONFIG.read_text())
    fake = FakeGitHub()
    converge(fake, REGISTRY, config)
    assert fake.writes == KEEPS


# Registered


def test_a_folder_already_laid_out_is_left_alone():
    """The claim the sync job rests on: it runs on every push to the default
    branch, so a push that changed no config must send nothing at all."""
    fake = registry_with(*SUBDIRS)
    assert folder_status(fake, REGISTRY, CONFIG).state == "registered"
    assert converge(fake, REGISTRY, CONFIG) == "unchanged"
    assert fake.writes == []


# Stale


def test_a_missing_subdirectory_is_put_back_alone():
    """Only what is absent is written, and the verb answers for the folder. A
    run that says ``unchanged`` and leaves a commit behind is the one claim that
    must not be wrong."""
    fake = registry_with("template")
    assert converge(fake, REGISTRY, CONFIG) == "updated"
    assert fake.writes == ["projects/glider/productions/.gitkeep"]


@pytest.mark.parametrize(
    ("laid_out", "absent"), [("template", "productions"), ("productions", "template")]
)
def test_a_folder_missing_a_subdirectory_is_stale(laid_out, absent):
    """Reading and writing must agree on what a folder is. ``converge`` lays out
    two things, so a read that looked at one would call a folder registered
    and then quietly change it. Either half missing is the same verdict, and
    the detail names the half to look for."""
    status = folder_status(registry_with(laid_out), REGISTRY, CONFIG)
    assert status.state == "stale"
    assert absent in status.detail


# Where a project's folder is, and what opens it


def test_the_folder_is_named_after_the_id():
    """One string names the config file and the registry folder, so there is
    nothing here to keep in step."""
    assert keep_path(CONFIG, "template") == "projects/glider/template/.gitkeep"


def test_the_token_has_one_name():
    """``REGISTRY_TOKEN`` is the one name this deployment uses."""
    with pytest.MonkeyPatch.context() as env:
        env.setenv("REGISTRY_TOKEN", "t")
        assert token_from_env() == "t"


def test_a_workflows_own_token_is_not_a_fallback():
    """A workflow's default token is scoped to the repository running it,
    not to the registry, and a token without access reads as 404, which the
    client turns into "no file yet". Falling back would report a project
    missing when the truth is a wrong token, green and wrong exactly where
    there is no write to catch it."""
    with pytest.MonkeyPatch.context() as env:
        env.delenv("REGISTRY_TOKEN", raising=False)
        env.setenv("GITHUB_TOKEN", "would-not-work")
        assert token_from_env() is None


# Which registry, and the refusal to guess


def test_where_to_write_is_read_from_the_environment():
    with pytest.MonkeyPatch.context() as env:
        env.setenv("REGISTRY_OWNER", "socib")
        env.setenv("REGISTRY_REPO", "dmp-registry")
        assert registry_from_env() == Registry(owner="socib", repo="dmp-registry")


def test_an_unset_coordinate_is_never_guessed():
    """No default, and both names reported at once. A default owner and repo
    would be one deployment's coordinates baked into every other, and a fork
    or a misconfigured job would write into this registry with nobody having
    said so."""
    with pytest.MonkeyPatch.context() as env:
        env.delenv("REGISTRY_OWNER", raising=False)
        env.delenv("REGISTRY_REPO", raising=False)
        with pytest.raises(RegistryError) as caught:
            registry_from_env()
    assert "REGISTRY_OWNER" in str(caught.value)
    assert "REGISTRY_REPO" in str(caught.value)


def test_the_coordinates_reach_the_client():
    """Threading the value through is only worth anything if it arrives, the
    calls are made against the registry that was asked for."""
    fake = FakeGitHub()
    converge(fake, Registry(owner="somebody", repo="theirs"), CONFIG)
    assert {call[:2] for call in fake.calls} == {("somebody", "theirs")}
