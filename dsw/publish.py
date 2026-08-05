"""Push a project's generated artifacts into a DS Wizard instance.

Reads what the generators wrote under ``build/`` and uploads it. It builds
nothing: run the generators first, and this only publishes what is already on
disk. In CI that "already on disk" is the artifact the ``generate`` job
uploaded, downloaded again — so what is published is what was built once, not
a second build nobody looked at.

Three targets, and they are three different things:

- ``km`` — the Knowledge Model bundle: the questionnaire itself.
- ``template`` — the Document Template bundle: how answers become a maDMP.
- ``submission`` — this project's submission service: a Document Submission
  entry pointing the fixed webhook at the project's registry folder
  (``?project=<id>``), scoped to the project's own template so that only its
  documents can submit to it.

``all`` runs them in that order, and the order is load-bearing: ``submission``
needs the uuid of the template just published.

**The first two publish a package; the third edits the instance.** A KM and a
template are DSW packages — an identity, a version, immutable — so publishing
them is idempotent *through the version*: an already-published ``package_id``
is skipped rather than rejected, and bumping the config's ``version`` is what
publishes a change. A submission service is an entry in the tenant's own
configuration: mutable, upserted by id, sitting beside other projects' entries.
Two different objects, two different ways of being idempotent, which is why
they are three targets and not one.

All three ask the instance before they act, and the third has its own reason
to: the API has no endpoint for one service, so writing it means sending the
tenant's *entire* configuration back — organisation, authentication, look and
feel, everything. Anything changed in the console between the read and the
write is silently reverted. So this compares what the service should say with
what it says, and sends nothing when they agree; the window then opens only on
the runs that had something to change.

Registering the project's folder in the registry is **not** here — it is
:mod:`registry`, and it runs in CI long before anything is published. What is
here is the guarantee that used to depend on the order of these targets:
``submission`` refuses to advertise a route to a folder that does not exist.

Every coordinate comes from the environment, and **none has a default**: where
a program writes is not something it may assume. ``DSW_API_URL``, ``DSW_EMAIL``
and ``DSW_PASSWORD`` say which instance and as whom; ``SUBMISSION_URL`` and
``SUBMISSION_TOKEN`` are the webhook's address as *DSW* reaches it and the
secret it checks, and are asked for by the one target that needs them.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from configs import ConfigFileError, load_config_file
from dsw.common import BUILD_DIR, package_id
from dsw.uuids import u
from registry import (
    GitHubClient,
    GitHubError,
    RegistryError,
    folder_status,
    registry_from_env,
    token_from_env,
)
from utils.errors import ProblemsError

KM_DIR = BUILD_DIR / "km"
TEMPLATE_DIR = BUILD_DIR / "template"

# The JSON output format of the generated document template (see
# generate_template.FORMATS): the format a submitted document is rendered in,
# so the submission service can name it without reading the bundle back.
JSON_FORMAT_UUID = u("template", "format", "JSON")

NIL_UUID = "00000000-0000-0000-0000-000000000000"
LISTING_PAGE_SIZE = 1000


class PublishError(ProblemsError):
    """Publishing cannot proceed as the environment or the registry stands."""

    noun = "publish problem"


class DswError(RuntimeError):
    """The instance rejected a call the caller cannot recover from."""

    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"DSW API error {status}: {message}")


# Where to publish, and as whom


@dataclass(frozen=True)
class Instance:
    """Which DSW instance this deployment publishes to, and as whom.

    A value, not a constant, and read from the environment with **no default**.
    A default endpoint would be one deployment's coordinates baked into every
    other's — and unlike a wrong registry, a wrong instance is not caught by
    anything downstream: it accepts the package and nobody is any the wiser.
    """

    api_url: str
    email: str
    password: str


def _required_env(names: tuple[str, ...], what: dict[str, str]) -> list[str]:
    """The values, or every name that is missing at once — a half-configured
    environment is fixed faster from the whole list than one name per run."""
    values = [os.environ.get(name) for name in names]
    missing = [name for name, value in zip(names, values, strict=True) if not value]
    if missing:
        raise PublishError([f"{name} is not set; it {what[name]}." for name in missing])
    return values


def instance_from_env() -> Instance:
    """Which instance to publish to, or every name it is missing at once."""
    return Instance(
        *_required_env(
            ("DSW_API_URL", "DSW_EMAIL", "DSW_PASSWORD"),
            {
                "DSW_API_URL": "says which DSW instance to publish to",
                "DSW_EMAIL": "says as whom",
                "DSW_PASSWORD": "authenticates that account",
            },
        )
    )


@dataclass(frozen=True)
class Webhook:
    """Where a submission service sends the document, and the secret it sends
    with it.

    The address is the fixed webhook as **DSW** reaches it: a compose service
    name locally, a public URL in a deployment. Both names are asked for by the
    ``submission`` target alone, because neither is a coordinate of the
    instance: publishing a KM must not require knowing where documents will one
    day be sent.

    The secret is as required as the address. The webhook answers 500 when it
    holds none and 401 when the header does not match, so a service written
    without one is a Submit button that fails every time — and it would be
    written *over* a service that worked, on nothing more than one name missing
    from one run.
    """

    url: str
    token: str


def webhook_from_env() -> Webhook:
    """Where submitted documents go, or every name it is missing at once."""
    return Webhook(
        *_required_env(
            ("SUBMISSION_URL", "SUBMISSION_TOKEN"),
            {
                "SUBMISSION_URL": "says where DSW sends a submitted document",
                "SUBMISSION_TOKEN": (
                    "is the shared secret the webhook checks, without which it "
                    "rejects every submission"
                ),
            },
        )
    )


# Talking to DSW


class DswClient:
    """The wizard-api calls this repository needs.

    Standard library only and synchronous, like the GitHub client: publishing a
    project is a handful of calls, not traffic. The transport ends here —
    bearer tokens, multipart bodies and status codes are its business alone.
    """

    def __init__(self, api_url: str, token: str):
        self.api_url = api_url.rstrip("/")
        self.token = token

    @classmethod
    def login(cls, instance: Instance) -> DswClient:
        """Authenticate and return a client for that instance.

        A constructor rather than a free function: the token is not read from
        the environment like the registry's, it is *obtained by a call* — so
        the thing that makes calls is what makes that one. It is also the call
        most likely to fail, a wrong password or an instance that is not up, so
        it reports both cases by name rather than surfacing a urllib traceback.
        """
        api_url = instance.api_url.rstrip("/")
        request = urllib.request.Request(
            f"{api_url}/tokens",
            data=json.dumps(
                {"email": instance.email, "password": instance.password}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            token = json.loads(urllib.request.urlopen(request, timeout=30).read())
        except urllib.error.HTTPError as e:
            raise PublishError(
                [
                    (
                        f"{instance.api_url} rejected the login for "
                        f"{instance.email!r} ({e.code}): {e.read().decode()}"
                    )
                ]
            ) from e
        except urllib.error.URLError as e:
            raise PublishError(
                [f"no DSW instance reachable at {instance.api_url} ({e.reason})"]
            ) from e
        return cls(api_url, token["token"])

    def _request(self, method: str, path: str, payload: Any | None = None) -> Any:
        request = urllib.request.Request(
            self.api_url + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as e:
            raise DswError(e.code, f"{method} {path}: {e.read().decode()}") from e

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, payload: Any) -> Any:
        return self._request("POST", path, payload)

    def put(self, path: str, payload: Any) -> Any:
        return self._request("PUT", path, payload)

    def post_bundle(
        self, path: str, filename: str, content_type: str, data: bytes
    ) -> dict[str, Any]:
        """POST a multipart file upload to a bundle endpoint."""
        boundary = "----FormBoundary" + uuid.uuid4().hex[:16]
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; '
                f'filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        request = urllib.request.Request(
            self.api_url + path,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            raise DswError(e.code, f"POST {path}: {e.read().decode()}") from e

    def list_all(self, endpoint: str, collection: str) -> list[dict[str, Any]]:
        """Every item of a paginated listing.

        Follows the page count instead of trusting one large page: a truncated
        listing would answer "not published" about something that is, and that
        answer decides whether a republish happens.
        """
        separator = "&" if "?" in endpoint else "?"
        first = self.get(f"{endpoint}{separator}size={LISTING_PAGE_SIZE}")
        items = list(first["_embedded"][collection])
        total_pages = (first.get("page") or {}).get("totalPages", 1)
        for number in range(1, total_pages):
            page = self.get(
                f"{endpoint}{separator}size={LISTING_PAGE_SIZE}&page={number}"
            )
            items.extend(page["_embedded"][collection])
        return items


def published_ids(items: list[dict[str, Any]], id_key: str) -> dict[str, str]:
    """A listing as ``package_id -> uuid``. The API routes packages by uuid
    while its listings spell the id out in three fields, so the two names of
    one package are reconciled here and nowhere else."""
    return {
        f"{item['organizationId']}:{item[id_key]}:{item['version']}": item["uuid"]
        for item in items
    }


def _package_ids(
    client: DswClient, endpoint: str, collection: str, id_key: str
) -> dict[str, str]:
    return published_ids(client.list_all(endpoint, collection), id_key)


def _find_package_uuid(
    client: DswClient, endpoint: str, collection: str, id_key: str, pid: str
) -> str:
    """The DSW uuid of a published package (KM or document template)."""
    uuid_ = _package_ids(client, endpoint, collection, id_key).get(pid)
    if uuid_ is None:
        raise PublishError(
            [
                (
                    f"no published package {pid!r} on the instance "
                    f"({endpoint}); publish it first"
                )
            ]
        )
    return uuid_


def _package_exists(
    client: DswClient, endpoint: str, collection: str, id_key: str, pid: str
) -> bool:
    """Whether ``pid`` is already published. DSW versions are immutable, so
    this is what makes publishing idempotent: the version is the sole gate,
    and running publish on an unchanged config does nothing."""
    return pid in _package_ids(client, endpoint, collection, id_key)


# The three targets


def publish_km(client: DswClient, km_path: Path) -> None:
    result = client.post_bundle(
        "/knowledge-model-packages/bundle",
        "km.km",
        "application/json",
        km_path.read_bytes(),
    )
    print(
        f"KM published: {result.get('organizationId')}:{result.get('kmId')}:"
        f"{result.get('version')}"
    )


def publish_template(client: DswClient, template_path: Path) -> None:
    """Publish a Document Template bundle, zipped on the fly — the endpoint
    expects a ``template/template.json`` archive."""
    bundle = json.loads(template_path.read_text())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "template/template.json", json.dumps(bundle, ensure_ascii=False)
        )
    result = client.post_bundle(
        "/document-templates/bundle",
        "tpl.zip",
        "application/zip",
        buffer.getvalue(),
    )
    print(f"Template published: {result.get('name')} ({result.get('uuid')})")


def submission_service(
    config: dict[str, Any],
    template_uuid: str,
    tenant_uuid: str,
    webhook: Webhook,
) -> dict[str, Any]:
    """One project's Document Submission entry.

    A pure function on purpose: what a submission service *says* is decided
    here and tested without an instance, while installing it is
    :func:`publish_submission`'s job. It cannot be generated ahead of time
    though — ``template_uuid`` is assigned by DSW and changes at every publish,
    and ``tenant_uuid`` is read from the instance — which is why it lives here
    and not beside the generators.

    Two things make it this project's and no other's: the folder in the URL,
    which is the *only* routing input the webhook has, and ``supportedFormats``
    naming this project's own template — so the Submit menu offers this service
    for this project's documents and for nothing else.

    Being pure is also what lets the caller compare it to what the instance
    already holds: two calls with the same inputs give the same document, so an
    equal one means there is nothing to write.
    """
    folder = config["id"]
    return {
        "id": folder,
        "name": f"{config['name']} → dmp-registry/{folder}",
        "description": "",
        "props": [],
        "request": {
            "headers": {"Authorization": f"Bearer {webhook.token}"},
            "method": "POST",
            "multipart": {"enabled": False, "fileName": ""},
            "url": f"{webhook.url}?project={folder}",
        },
        "supportedFormats": [
            {
                "serviceId": folder,
                "templateUuid": template_uuid,
                "formatUuid": JSON_FORMAT_UUID,
                "tenantUuid": tenant_uuid,
            }
        ],
    }


def _require_registered(config: dict[str, Any]) -> None:
    """Refuse to advertise a route to a folder that is not there.

    The webhook rejects a folder with no ``meta.yaml``, so a submission service
    pointing at an unregistered folder turns every Submit into a failure the
    researcher gets blamed for. Holding that by the order of the targets would
    be holding it by a convention, and a convention is what gets skipped when
    somebody runs one target by hand.

    Which registry to look in comes from the environment like everywhere else:
    checking the wrong one would answer "registered" about a folder in a
    repository nobody submits to.
    """
    token = token_from_env()
    if not token:
        raise PublishError(
            [
                (
                    "REGISTRY_TOKEN is not set, so the project's registry "
                    "folder cannot be checked — and a submission service "
                    "pointing at a folder that does not exist turns every "
                    "Submit into a failure (locally: "
                    "REGISTRY_TOKEN=$(gh auth token))"
                )
            ]
        )
    status = folder_status(GitHubClient(token=token), registry_from_env(), config)
    if status.state == "missing":
        raise PublishError(
            [
                (
                    f"{config['id']!r} is not registered yet: the webhook "
                    f"refuses a folder with no meta.yaml. Push to the default "
                    f"branch, or run scripts/sync_registry.py"
                )
            ]
        )
    if status.state == "collision":
        raise PublishError([status.detail])


def publish_submission(client: DswClient, config: dict[str, Any], pid: str) -> None:
    """Create or refresh this project's submission service. An upsert by
    service id: other projects' services are left untouched. A new template
    version gets a new uuid, so this has to run after ``template``.

    The write is skipped when the service already says exactly this and
    submissions are enabled — the ``PUT`` carries the whole tenant
    configuration, so not making it is how a run that changes nothing cannot
    revert anything either.
    """
    _require_registered(config)
    webhook = webhook_from_env()

    folder = config["id"]
    template_uuid = _find_package_uuid(
        client, "/document-templates", "documentTemplates", "templateId", pid
    )
    tenant = client.get("/tenants/current/config")
    submission = tenant.setdefault("submission", {})
    services = submission.setdefault("services", [])
    tenant_uuid = next(
        (s["tenantUuid"] for s in services if s.get("tenantUuid")), NIL_UUID
    )
    service = submission_service(config, template_uuid, tenant_uuid, webhook)
    current = next((s for s in services if s.get("id") == folder), None)
    if current == service and submission.get("enabled"):
        print(f"Submission service {folder!r} unchanged (template {template_uuid}).")
        return

    submission["enabled"] = True
    services[:] = [s for s in services if s.get("id") != folder] + [service]
    client.put("/tenants/current/config", tenant)
    print(
        f"Submission service {folder!r} -> {service['request']['url']} "
        f"(template {template_uuid})"
    )


def _artifact(directory: Path, name: str, generator: str) -> Path:
    path = directory / name
    if not path.exists():
        raise PublishError([f"not found: {path} — run {generator} first"])
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=["km", "template", "submission", "all"])
    parser.add_argument("config", help="path to a project config")
    args = parser.parse_args(argv)

    try:
        config = load_config_file(args.config)
        instance = instance_from_env()
        client = DswClient.login(instance)
    except (ConfigFileError, PublishError) as err:
        print(err, file=sys.stderr)
        return 1

    pid = package_id(config)
    artifact_id = config["id"]

    try:
        if args.target in ("km", "all"):
            if _package_exists(
                client,
                "/knowledge-model-packages",
                "knowledgeModelPackages",
                "kmId",
                pid,
            ):
                print(
                    f"KM {pid} already published — bump `version` to publish a change."
                )
            else:
                publish_km(
                    client, _artifact(KM_DIR, f"{artifact_id}_km.km", "dsw.generate_km")
                )

        if args.target in ("template", "all"):
            if _package_exists(
                client, "/document-templates", "documentTemplates", "templateId", pid
            ):
                print(
                    f"Template {pid} already published — bump `version` to "
                    f"publish a change."
                )
            else:
                publish_template(
                    client,
                    _artifact(
                        TEMPLATE_DIR,
                        f"{artifact_id}_template.json",
                        "dsw.generate_template",
                    ),
                )

        if args.target in ("submission", "all"):
            publish_submission(client, config, pid)
    except (PublishError, RegistryError, GitHubError, DswError) as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
