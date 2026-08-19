"""Publishing, minus the instance.

Nothing here reaches a DSW instance, what is worth testing is what publish
decides before it calls anything: where it was told to publish, which package
is already there, what a submission service says, and the one refusal that
keeps a researcher from meeting a broken Submit button.

The uploads themselves are three lines of urllib each and are the instance's
answer, not ours.
"""

import json
from pathlib import Path

import pytest
import yaml

from dsw.common import package_id
from dsw.generate_template import build_template_bundle
from dsw.publish import (
    SUBMISSION_FORMAT_UUID,
    DswClient,
    Instance,
    PublishError,
    Webhook,
    _artifact,
    _require_registered,
    installed_service,
    instance_from_env,
    publish_submission,
    published_ids,
    submission_service,
    webhook_from_env,
)
from project import assemble_project
from registry import Registry

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
    """Every missing name at once, and none of the three has a default,
    because a wrong instance is caught by nothing downstream, it accepts the
    package."""
    no_env.setenv("DSW_EMAIL", "a@b.c")
    with pytest.raises(PublishError) as err:
        instance_from_env()
    assert len(err.value.problems) == 2
    assert "DSW_API_URL" in str(err.value) and "DSW_PASSWORD" in str(err.value)


def test_publishing_a_package_does_not_require_the_webhook(no_env):
    """The webhook's two names are not coordinates of the instance, the
    target that needs them is the only one that asks."""
    for name, value in zip(DSW_NAMES, ("http://dsw/api", "a@b.c", "pw"), strict=True):
        no_env.setenv(name, value)
    instance_from_env()
    with pytest.raises(PublishError, match="SUBMISSION_URL"):
        webhook_from_env()


def test_the_shared_secret_is_as_required_as_the_address(no_env):
    """The webhook answers 500 holding no secret and 401 on a mismatch, so a
    service written without one is a Submit button that fails every time, and
    it would be written over a service that worked."""
    with pytest.raises(PublishError) as err:
        webhook_from_env()
    assert len(err.value.problems) == 2
    assert "SUBMISSION_TOKEN" in str(err.value)


# Which package is already published


def test_a_listing_is_read_as_the_three_names_of_one_package():
    """DSW routes by uuid but spells a package out in three fields, and this
    is where the two names are reconciled."""
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


WEBHOOK = Webhook("http://w", "s3cret")
REGISTRY = Registry("an-owner", "a-registry")

# What the instance stamps on a service of its own accord, and hands back on
# the next read. A `PUT` takes none of it, it is assigned and not declared.
TENANT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def as_dsw_returns_it(service: dict) -> dict:
    """The same service, in the shape ``GET /tenants/current/config`` gives
    it back, a tenant uuid on the service and on each supported format, the
    service id repeated inside the format, and the two timestamps.

    Every fixture below goes through this, and that is the point: a fake that
    hands back what `publish.py` writes is a fake that agrees with the code
    about a shape neither of them owns. This one agrees with DSW.
    """
    return {
        **service,
        "tenantUuid": TENANT,
        "createdAt": "2026-07-01T10:00:00.000Z",
        "updatedAt": "2026-07-01T10:00:00.000Z",
        "supportedFormats": [
            {**fmt, "tenantUuid": TENANT, "serviceId": service["id"]}
            for fmt in service["supportedFormats"]
        ],
    }


def test_the_service_routes_by_folder_and_only_by_folder(config):
    """The folder in the URL is the only routing input the webhook has,
    which project a submission belongs to is decided there and never by
    reading the document."""
    service = submission_service(config, "template-uuid", WEBHOOK, REGISTRY)
    assert service["id"] == "glider"
    assert service["request"]["url"] == "http://w?project=glider"


def test_the_service_carries_the_shared_secret(config):
    """What DSW sends is what the webhook compares against its own copy."""
    service = submission_service(config, "template-uuid", WEBHOOK, REGISTRY)
    assert service["request"]["headers"] == {"Authorization": "Bearer s3cret"}


def test_the_service_is_scoped_to_this_project_s_own_template(config):
    """So the Submit menu offers it for this project's documents and for
    nothing else. Two fields and no more: a supported format is stored with a
    tenant uuid and its service id too, and neither is this run's to send."""
    service = submission_service(config, "template-uuid", WEBHOOK, REGISTRY)
    assert service["supportedFormats"] == [
        {"templateUuid": "template-uuid", "formatUuid": SUBMISSION_FORMAT_UUID}
    ]


def test_the_service_names_a_format_the_template_bundle_actually_carries(config):
    """The third thing this module and a generator must answer identically.
    `publish` names a format uuid in the submission service,
    `generate_template` emits the formats a template has, neither reads the
    other and they run in different runs. A service naming a format the bundle
    does not carry is an entry in the Submit menu that produces nothing.

    Both derive it from `common`, so this builds a real bundle and looks for
    the uuid in it."""
    project = assemble_project(GLIDER_CONFIG)
    bundle = build_template_bundle(project, created_at="2026-01-01T00:00:00.000Z")
    service = submission_service(config, "tpl-uuid", WEBHOOK, REGISTRY)

    emitted = {fmt["uuid"] for fmt in bundle["formats"]}
    assert service["supportedFormats"][0]["formatUuid"] in emitted


def test_a_service_this_module_builds_is_already_what_a_write_carries(config):
    """The two halves of one fact, tied together so neither can drift. What
    `submission_service` declares is exactly what `installed_service` keeps,
    so a field added to one and forgotten in the other cannot quietly drop out
    of the comparison."""
    service = submission_service(config, "tpl-uuid", WEBHOOK, REGISTRY)
    assert installed_service(service) == service


def test_what_the_instance_stamped_on_a_service_is_not_a_difference(config):
    """A read gives back more than a write takes. Those extra fields are the
    instance's own answer, not something this run has an opinion about, so they
    cannot be read as a disagreement."""
    service = submission_service(config, "tpl-uuid", WEBHOOK, REGISTRY)
    assert installed_service(as_dsw_returns_it(service)) == service


# Writing it: only when it would say something else


class _Instance(DswClient):
    """A DSW instance reduced to what `publish_submission` reads, one
    published document template and a tenant configuration it may rewrite.
    Subclassing the client rather than faking it keeps the paging and the id
    reconciliation under test, which are what decide which uuid the service
    names."""

    def __init__(self, config, services, enabled=True):
        super().__init__("http://dsw/api", "a-token")
        org, template_id, version = package_id(config).split(":")
        self.template = {
            "organizationId": org,
            "templateId": template_id,
            "version": version,
            "uuid": "tpl-uuid",
        }
        self.tenant = {
            "organization": {"name": "SOCIB"},
            "submission": {"enabled": enabled, "services": list(services)},
        }
        self.puts = []

    def get(self, path):
        if path.startswith("/document-templates"):
            return {
                "_embedded": {"documentTemplates": [self.template]},
                "page": {"totalPages": 1},
            }
        return self.tenant

    def put(self, path, payload):
        self.puts.append(payload)


@pytest.fixture
def submission_env(monkeypatch):
    """Registered, and told where to submit, the two things the target
    checks before it looks at the instance at all."""
    monkeypatch.setenv("SUBMISSION_URL", "http://w")
    monkeypatch.setenv("SUBMISSION_TOKEN", "s3cret")
    monkeypatch.setenv("REGISTRY_TOKEN", "a-token")
    monkeypatch.setenv("REGISTRY_OWNER", REGISTRY.owner)
    monkeypatch.setenv("REGISTRY_REPO", REGISTRY.repo)
    monkeypatch.setattr("dsw.publish.folder_status", _Registry("registered"))
    return monkeypatch


def _current(config):
    """The service the instance would already hold, published from this very
    config against this very template, and handed back the way DSW hands one
    back."""
    return as_dsw_returns_it(submission_service(config, "tpl-uuid", WEBHOOK, REGISTRY))


def test_a_service_that_already_says_this_is_not_written_again(config, submission_env):
    """The PUT carries the tenant's whole configuration, so a run with
    nothing to change must not make it, which is what stops it from reverting
    a setting edited in the console since the GET.

    The instance returns a service carrying a tenant uuid and two timestamps
    of its own, so the comparison has to be made on the written fields alone
    for "unchanged" ever to come out true."""
    client = _Instance(config, [_current(config)])
    publish_submission(client, config, package_id(config))
    assert client.puts == []


@pytest.mark.parametrize(
    "existing, enabled",
    [
        pytest.param([], True, id="no service yet"),
        pytest.param(
            [{"id": "glider", "request": {"url": "http://old"}}],
            True,
            id="a service saying something else",
        ),
        pytest.param(None, False, id="the right service, submissions turned off"),
    ],
)
def test_anything_else_is_written(config, submission_env, existing, enabled):
    """Equal is not enough on its own, a service nobody can reach because
    submissions are disabled is a Submit button that is not there."""
    services = [_current(config)] if existing is None else existing
    client = _Instance(config, services, enabled=enabled)
    publish_submission(client, config, package_id(config))
    assert len(client.puts) == 1
    written = client.puts[0]["submission"]
    assert written["enabled"] is True
    assert [s["id"] for s in written["services"]] == ["glider"]
    assert written["services"][0]["supportedFormats"][0]["templateUuid"] == "tpl-uuid"


def test_other_projects_services_are_left_untouched(config, submission_env):
    """An upsert by service id, this repository publishes one project at a
    time into a tenant that hosts them all."""
    other = {"id": "hf-radar", "request": {"url": "http://w?project=hf-radar"}}
    client = _Instance(config, [other])
    publish_submission(client, config, package_id(config))
    services = client.puts[0]["submission"]["services"]
    assert other in services
    assert [s["id"] for s in services] == ["hf-radar", "glider"]


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
    """The webhook refuses a folder that is not laid out, so advertising a
    route to one turns every Submit into a failure."""
    registered_env.setattr("dsw.publish.folder_status", _Registry("missing"))
    with pytest.raises(PublishError, match="not registered yet"):
        _require_registered(config)


@pytest.mark.parametrize("state", ["registered", "stale"])
def test_a_registered_folder_lets_it_through(config, registered_env, state):
    """`stale` too, a subdirectory to put back is a sync away and the folder
    is there, which is what the webhook needs."""
    registered_env.setattr("dsw.publish.folder_status", _Registry(state))
    _require_registered(config)


def test_no_token_means_the_check_cannot_be_made_and_it_stops(config, monkeypatch):
    """Refusing beats assuming, the point is not to advertise a route nobody
    verified."""
    monkeypatch.delenv("REGISTRY_TOKEN", raising=False)
    with pytest.raises(PublishError, match="cannot be checked"):
        _require_registered(config)


# The bundle on disk is the one this config asks for


def _bundle(tmp_path, pid):
    path = tmp_path / "glider_km.km"
    path.write_text(json.dumps({"id": pid, "packages": []}))
    return path


def test_a_bundle_that_was_never_built_names_the_generator(tmp_path):
    with pytest.raises(PublishError, match="run dsw.generate_km first"):
        _artifact(tmp_path / "glider_km.km", "dsw.generate_km", "socib:glider:1.0.2")


def test_a_bundle_built_for_another_version_is_not_published(tmp_path, config):
    """The file name carries no version, so a `version` bumped without
    regenerating leaves the previous bundle exactly where the new one goes.
    Nothing downstream catches it, the listing is asked about the new id,
    says "not published", and the old bundle goes up under the version it was
    built with, the run printing a success that names neither the version the
    config asks for nor the one it published."""
    stale = _bundle(tmp_path, "socib:glider:1.0.1")
    with pytest.raises(PublishError, match="was built for 'socib:glider:1.0.1'"):
        _artifact(stale, "dsw.generate_km", package_id(config))


def test_a_bundle_built_for_this_config_goes_through(tmp_path, config):
    pid = package_id(config)
    assert _artifact(_bundle(tmp_path, pid), "dsw.generate_km", pid) == _bundle(
        tmp_path, pid
    )


def test_a_bundle_that_is_not_a_bundle_says_so(tmp_path):
    """Rather than a traceback out of the middle of a publish."""
    path = tmp_path / "glider_km.km"
    path.write_text("half a file")
    with pytest.raises(PublishError, match="cannot be read as a bundle"):
        _artifact(path, "dsw.generate_km", "socib:glider:1.0.2")
