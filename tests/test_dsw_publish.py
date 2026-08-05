"""Publishing, minus the instance.

Nothing here reaches a DSW instance: what is worth testing is what publish
*decides* before it calls anything — where it was told to publish, which
package is already there, what a submission service says, and the one refusal
that keeps a researcher from meeting a broken Submit button.

The uploads themselves are three lines of urllib each and are the instance's
answer, not ours.
"""

from pathlib import Path

import pytest
import yaml

from dsw.publish import (
    JSON_FORMAT_UUID,
    Instance,
    PublishError,
    _require_registered,
    instance_from_env,
    published_ids,
    submission_service,
    submission_token_from_env,
    submission_url_from_env,
)

GLIDER_CONFIG = Path(__file__).parent.parent / "configs" / "projects" / "glider.yaml"

DSW_NAMES = ("DSW_API_URL", "DSW_EMAIL", "DSW_PASSWORD")


@pytest.fixture
def config():
    return yaml.safe_load(GLIDER_CONFIG.read_text())


@pytest.fixture
def no_env(monkeypatch):
    """A clean environment: every name this module reads, unset."""
    for name in (*DSW_NAMES, "SUBMISSION_URL", "SUBMISSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# Where to publish is read, never assumed


def test_where_to_publish_is_read_from_the_environment(no_env):
    for name, value in zip(DSW_NAMES, ("http://dsw/api", "a@b.c", "pw"), strict=True):
        no_env.setenv(name, value)
    assert instance_from_env() == Instance("http://dsw/api", "a@b.c", "pw")


def test_a_missing_coordinate_names_every_missing_one_at_once(no_env):
    """A half-configured environment is fixed faster from the whole list than
    one name per run — and none of the three has a default, because a wrong
    instance is caught by nothing downstream: it accepts the package."""
    no_env.setenv("DSW_EMAIL", "a@b.c")
    with pytest.raises(PublishError) as err:
        instance_from_env()
    assert len(err.value.problems) == 2
    assert "DSW_API_URL" in str(err.value) and "DSW_PASSWORD" in str(err.value)


def test_publishing_a_package_does_not_require_the_webhook_address(no_env):
    """`SUBMISSION_URL` is the webhook's address, not a coordinate of the
    instance: the target that needs it is the only one that asks."""
    for name, value in zip(DSW_NAMES, ("http://dsw/api", "a@b.c", "pw"), strict=True):
        no_env.setenv(name, value)
    instance_from_env()
    with pytest.raises(PublishError, match="SUBMISSION_URL"):
        submission_url_from_env()


def test_a_missing_shared_secret_is_not_an_error(no_env):
    """A webhook deployed without one accepts unauthenticated calls; refusing
    to configure the service would be refusing a deployment that works."""
    assert submission_token_from_env() is None


# Which package is already published


def test_a_listing_is_read_as_the_three_names_of_one_package():
    """DSW routes by uuid but spells a package out in three fields; this is the
    only place the two names are reconciled."""
    items = [
        {
            "organizationId": "socib",
            "kmId": "glider",
            "version": "1.0.0",
            "uuid": "km-uuid",
        },
        {
            "organizationId": "socib",
            "kmId": "glider",
            "version": "2.0.0",
            "uuid": "newer",
        },
    ]
    assert published_ids(items, "kmId") == {
        "socib:glider:1.0.0": "km-uuid",
        "socib:glider:2.0.0": "newer",
    }


# What a submission service says


def test_the_service_routes_by_folder_and_only_by_folder(config):
    """The folder in the URL is the only routing input the webhook has: which
    project a submission belongs to is decided there, never by reading the
    document."""
    service = submission_service(config, "template-uuid", "tenant-uuid", "http://w", "")
    assert service["id"] == "glider"
    assert service["request"]["url"] == "http://w?project=glider"


def test_the_service_is_scoped_to_this_project_s_own_template(config):
    """So the Submit menu offers it for this project's documents and for
    nothing else."""
    service = submission_service(config, "template-uuid", "tenant-uuid", "http://w", "")
    assert service["supportedFormats"] == [
        {
            "serviceId": "glider",
            "templateUuid": "template-uuid",
            "formatUuid": JSON_FORMAT_UUID,
            "tenantUuid": "tenant-uuid",
        }
    ]


@pytest.mark.parametrize(
    "token, headers",
    [
        (None, {}),
        ("", {}),
        ("s3cret", {"Authorization": "Bearer s3cret"}),
    ],
)
def test_no_shared_secret_means_no_authorization_header(config, token, headers):
    """An empty Bearer would authenticate nothing and read as if it did."""
    service = submission_service(config, "t", "n", "http://w", token)
    assert service["request"]["headers"] == headers


# The refusal that protects the researcher


class _Registry:
    def __init__(self, state):
        self.state = state

    def __call__(self, gh, registry, config):
        from registry.folder import FolderStatus

        return FolderStatus("glider", self.state, f"detail for {self.state}")


@pytest.fixture
def registered_env(monkeypatch):
    monkeypatch.setenv("REGISTRY_TOKEN", "a-token")
    monkeypatch.setenv("REGISTRY_OWNER", "owner")
    monkeypatch.setenv("REGISTRY_REPO", "dmp-registry")
    return monkeypatch


def test_an_unregistered_folder_stops_the_submission_service(config, registered_env):
    """The webhook refuses a folder with no meta.yaml, so advertising a route
    to one turns every Submit into a failure the researcher gets blamed for.
    Holding that by the order of the targets would hold it by a convention."""
    registered_env.setattr("dsw.publish.folder_status", _Registry("missing"))
    with pytest.raises(PublishError, match="not registered yet"):
        _require_registered(config)


def test_a_collision_stops_it_too(config, registered_env):
    registered_env.setattr("dsw.publish.folder_status", _Registry("collision"))
    with pytest.raises(PublishError, match="detail for collision"):
        _require_registered(config)


@pytest.mark.parametrize("state", ["registered", "stale"])
def test_a_registered_folder_lets_it_through(config, registered_env, state):
    """`stale` too: meta.yaml no longer matching the config is a sync away,
    and the folder is there, which is what the webhook needs."""
    registered_env.setattr("dsw.publish.folder_status", _Registry(state))
    _require_registered(config)


def test_no_token_means_the_check_cannot_be_made_and_it_stops(config, monkeypatch):
    """Refusing beats assuming: the whole point is not to advertise a route
    nobody verified."""
    monkeypatch.delenv("REGISTRY_TOKEN", raising=False)
    with pytest.raises(PublishError, match="cannot be checked"):
        _require_registered(config)
