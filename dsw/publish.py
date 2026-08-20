"""Push a project's generated artifacts into a DS Wizard instance.

Reads what the generators wrote under ``build/`` and uploads it. It builds
nothing, run the generators first. A bundle names its own package id, and
``_artifact()`` confronts it with the config before anything is uploaded.

Three targets, and they are three different things:

- ``km``, the Knowledge Model bundle, the questionnaire itself
- ``template``, the Document Template bundle, how answers become a maDMP
- ``submission``, this project's submission service, a Document Submission
  entry pointing the fixed webhook at the project's registry folder
  (``?project=<id>``), scoped to the project's own template so that only its
  documents can submit to it

``all`` runs them in that order, and the order is load-bearing, ``submission``
needs the uuid of the template just published. It also refuses to advertise a
route to a folder that does not exist.

The first two publish a package, the third edits the instance. A KM and a
template are DSW packages, an identity, a version, immutable, so publishing
them is idempotent through the version: an already-published ``package_id`` is
skipped rather than rejected, and bumping the config's ``version`` is what
publishes a change. A submission service is an entry in the tenant's own
configuration, mutable, upserted by id, sitting beside other projects'
entries.

The API has no endpoint for one service, so writing it means sending the
tenant's entire configuration back, and anything changed in the console
between the read and the write is silently reverted. This compares what the
service should say with what it says, and sends nothing when they agree. The
comparison is made over what a write carries, not over what a read gives back,
the instance returning a service richer than the one it accepts.

Every coordinate comes from the environment and none has a default.
``DSW_API_URL``, ``DSW_EMAIL`` and ``DSW_PASSWORD`` say which instance and as
whom, ``SUBMISSION_URL`` and ``SUBMISSION_TOKEN`` are the webhook's address as
DSW reaches it and the secret it checks, asked for by the one target that
needs them.
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
from dsw.common import (
    SUBMISSION_FORMAT,
    format_uuid,
    km_path,
    package_id,
    template_path,
)
from registry import (
    Registry,
    RegistryError,
    folder_status,
    registry_from_env,
    token_from_env,
)
from utils.errors import ProblemsError
from utils.github import GitHubClient, GitHubError

# The format a submitted document is rendered in, so the submission service can
# name it without reading the template bundle back. Both the name and the
# derivation come from `common`, this and generate_template must answer with
# the same uuid.
SUBMISSION_FORMAT_UUID = format_uuid(SUBMISSION_FORMAT)

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

    A value, not a constant, read from the environment with no default. Unlike
    a wrong registry, a wrong instance is caught by nothing downstream, it
    accepts the package and nobody is any the wiser.
    """

    api_url: str
    email: str
    password: str


def _required_env(names: tuple[str, ...], what: dict[str, str]) -> list[str]:
    """The values, or every name that is missing at once."""
    values = [os.environ.get(name) for name in names]
    missing = [name for name, value in zip(names, values, strict=True) if not value]
    if missing:
        raise PublishError([f"{name} is not set, it {what[name]}." for name in missing])
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

    The address is the fixed webhook as DSW reaches it, a compose service name
    locally, a public URL in a deployment. Route included, a service is built
    by appending ``?project=<id>`` and nothing else, so an address given
    without the webhook's own path writes a service that posts to the
    container root.

    The secret is as required as the address. The webhook answers 500 when it
    holds none and 401 when the header does not match.

    Either one wrong writes a Submit button that fails every time, over a
    service that worked, on a value nothing downstream can check.
    """

    url: str
    token: str


def webhook_from_env() -> Webhook:
    """Where submitted documents go, or every name it is missing at once."""
    return Webhook(
        *_required_env(
            ("SUBMISSION_URL", "SUBMISSION_TOKEN"),
            {
                "SUBMISSION_URL": (
                    "says where DSW sends a submitted document, route included "
                    "(publish only appends ?project=<id>)"
                ),
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

    Standard library only, and synchronous. The transport ends here, bearer
    tokens, multipart bodies and status codes are its business alone.
    """

    def __init__(self, api_url: str, token: str):
        self.api_url = api_url.rstrip("/")
        self.token = token

    @classmethod
    def login(cls, instance: Instance) -> DswClient:
        """Authenticate and return a client for that instance.

        The call most likely to fail, a wrong password or an instance that is
        not up, so it reports both by name rather than surfacing a urllib
        traceback.
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

        Follows the page count instead of trusting one large page, a truncated
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
    one package are reconciled here."""
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
                    f"({endpoint}), publish it first"
                )
            ]
        )
    return uuid_


def _package_exists(
    client: DswClient, endpoint: str, collection: str, id_key: str, pid: str
) -> bool:
    """Whether ``pid`` is already published. DSW versions are immutable, so
    the version is the sole gate and publishing an unchanged config does
    nothing.

    Exact of the latest version and of it alone, the listing returning one row
    per ``kmId``, so an older version answers "not published" while being
    perfectly present. A version only ever goes up, so the one being published
    is the latest, and replaying an old commit has DSW reject the upload
    rather than overwrite anything.
    """
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
    """Publish a Document Template bundle, zipped on the fly, the endpoint
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
    webhook: Webhook,
    registry: Registry,
) -> dict[str, Any]:
    """One project's Document Submission entry, in the shape a write takes.

    A pure function, what a submission service says is decided here and tested
    without an instance, while installing it is ``publish_submission()``'s job.

    Two things make it this project's and no other's: the folder in the URL,
    which is the only routing input the webhook has, and ``supportedFormats``
    naming this project's own template, so the Submit menu offers this service
    for this project's documents and for nothing else.

    The registry is here for the name alone, which is what a researcher reads
    in the Submit menu, so it says where the DMP goes rather than naming one
    repository for every deployment.

    Nothing here is the instance's to assign. A service is stored with a tenant
    uuid on itself and on each supported format, a service id repeated inside
    the format, and two timestamps, none of which a change payload carries.
    ``installed_service()`` is the other half of that fact.
    """
    folder = config["id"]
    return {
        "id": folder,
        "name": f"{config['name']} → {registry.repo}/{folder}",
        "description": "",
        "props": [],
        "request": {
            "headers": {"Authorization": f"Bearer {webhook.token}"},
            "method": "POST",
            "multipart": {"enabled": False, "fileName": ""},
            "url": f"{webhook.url}?project={folder}",
        },
        "supportedFormats": [
            {"templateUuid": template_uuid, "formatUuid": SUBMISSION_FORMAT_UUID}
        ],
    }


# What a write carries, at each of the two levels a service has one. The rest
# of what a read gives back, `tenantUuid` on both levels, `serviceId` inside
# the format, `createdAt` and `updatedAt`, is assigned by the instance.
_WRITTEN_SERVICE_FIELDS = ("id", "name", "description", "props", "request")
_WRITTEN_FORMAT_FIELDS = ("templateUuid", "formatUuid")


def installed_service(service: dict[str, Any]) -> dict[str, Any]:
    """A service the instance returned, read as the write contract sees it.

    A ``GET`` hands back the service as it is stored and a ``PUT`` takes the
    fields above and no others, so the two shapes never match as they stand
    and a comparison has to be made on the written fields alone. A field the
    instance assigned is not a field this run has an opinion about.
    """
    return {
        **{name: service.get(name) for name in _WRITTEN_SERVICE_FIELDS},
        "supportedFormats": [
            {name: fmt.get(name) for name in _WRITTEN_FORMAT_FIELDS}
            for fmt in service.get("supportedFormats") or []
        ],
    }


def _require_registered(config: dict[str, Any]) -> None:
    """Refuse to advertise a route to a folder that is not there.

    The webhook rejects a folder that is not laid out, so a submission service
    pointing at an unregistered folder turns every Submit into a failure.
    Which registry to look in comes from the environment like everywhere else.
    """
    token = token_from_env()
    if not token:
        raise PublishError(
            [
                (
                    "REGISTRY_TOKEN is not set, so the project's registry "
                    "folder cannot be checked, and a submission service "
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
                    f"refuses a folder that is not laid out. Push to the "
                    f"default branch, or run scripts/sync_registry.py"
                )
            ]
        )


def publish_submission(client: DswClient, config: dict[str, Any], pid: str) -> None:
    """Create or refresh this project's submission service. An upsert by
    service id: other projects' services are left untouched. A new template
    version gets a new uuid, so this has to run after ``template``.

    The write is skipped when the service already says exactly this and
    submissions are enabled, the ``PUT`` carrying the whole tenant
    configuration, so a run that changes nothing cannot revert anything
    either. What "exactly this" means is ``installed_service()``'s answer.
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
    service = submission_service(config, template_uuid, webhook, registry_from_env())
    current = next((s for s in services if s.get("id") == folder), None)
    unchanged = current is not None and installed_service(current) == service
    if unchanged and submission.get("enabled"):
        print(f"Submission service {folder!r} unchanged (template {template_uuid}).")
        return

    submission["enabled"] = True
    services[:] = [s for s in services if s.get("id") != folder] + [service]
    client.put("/tenants/current/config", tenant)
    print(
        f"Submission service {folder!r} -> {service['request']['url']} "
        f"(template {template_uuid})"
    )


def _artifact(path: Path, generator: str, pid: str) -> Path:
    """One generated bundle, checked to be the one this config asks for.

    A bundle names its own package id, and the file name does not carry a
    version, so a config whose ``version`` was bumped without regenerating
    leaves the previous bundle exactly where the new one would be. Nothing
    downstream catches it, the listing is asked about the new id, says "not
    published", and the old bundle goes up under the version it was built
    with. Publishing is the step with no undo, so the two are compared here.
    """
    if not path.exists():
        raise PublishError([f"not found: {path}, run {generator} first"])
    try:
        built = json.loads(path.read_text()).get("id")
    except (OSError, json.JSONDecodeError) as err:
        raise PublishError([f"{path} cannot be read as a bundle: {err}"]) from err
    if built != pid:
        raise PublishError(
            [
                (
                    f"{path} was built for {built!r} and this config asks for "
                    f"{pid!r}, re-run {generator}"
                )
            ]
        )
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
                    f"KM {pid} already published, bump `version` to publish a change."
                )
            else:
                publish_km(
                    client,
                    _artifact(km_path(artifact_id), "dsw.generate_km", pid),
                )

        if args.target in ("template", "all"):
            if _package_exists(
                client, "/document-templates", "documentTemplates", "templateId", pid
            ):
                print(
                    f"Template {pid} already published, bump `version` to "
                    f"publish a change."
                )
            else:
                publish_template(
                    client,
                    _artifact(template_path(artifact_id), "dsw.generate_template", pid),
                )

        if args.target in ("submission", "all"):
            publish_submission(client, config, pid)
    except (PublishError, RegistryError, GitHubError, DswError) as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
