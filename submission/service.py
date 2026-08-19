"""The webhook's logic, free of HTTP plumbing.

A document is checked against the rules its own envelope names before anything
is written, so a DMP that does not hold up never reaches the registry at all
and the researcher hears why while they are still in DSW. What the registry
holds is therefore what has passed, and it holds the verdict beside it.

Stateless: everything derives from the document, the folder and a small static
config. Nothing here creates a repository or any scaffolding, the folder and
its subdirectories are laid out beforehand from madmp-core.
"""

from __future__ import annotations

import base64
import json
import re
from collections import Counter
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

from project import RULES_DIR, merge_rules, resolve_pins
from quality_control import CheckResult, has_failures, run_qc
from submission.github_client import GitHubClient
from utils.errors import ProblemsError

# A safe folder slug: no dots or slashes, so a submission can never escape
# projects/<folder>/ (path traversal) or name anything but a folder.
_FOLDER_RE = re.compile(r"^[a-z0-9-]{1,64}$")

# (!!) The registry's default branch, and part of every dmp_id this webhook
# writes. A dmp_id is the DMP's stable identifier, so moving the registry to
# another branch would leave every identifier ever issued pointing nowhere.
_BRANCH = "main"

# The key the document template renders beside `dmp`, carrying the versions
# the document was built from.
_ENVELOPE = "metadata"


# How many violations a refusal spells out before counting the rest. DSW
# shows this message on the submission, not a report, and a document missing
# forty fields would push the beginning of it out of sight.
_SPELLED_OUT = 5

# The order the verdict counts them in, so two files always read the same way.
_STATUSES = ("pass", "fail", "warning", "missing")


class SubmissionError(ValueError):
    """The submission cannot be routed to a registry folder."""


class QualityControlError(ValueError):
    """The document does not hold up against the rules it names.

    Told apart from a routing failure because it is the one thing the
    researcher can fix, and the only one worth spelling out to them.
    """


@dataclass(frozen=True)
class SubmissionConfig:
    """Static webhook configuration (from the environment, see app.py)."""

    # Both required, neither defaulted: the values live in .env.example and
    # nowhere else, and app.py refuses to build this without them.
    github_owner: str  # account owning the dmp-registry repo
    registry_repo: str  # the mono-repo all projects live in


def _pins_are_well_formed(rules: Any) -> bool:
    """Whether `rules` is a non-empty list of one-key mappings of strings,
    which is the shape a pinned rules version is written in."""
    return (
        isinstance(rules, list)
        and bool(rules)
        and all(
            isinstance(pin, dict)
            and len(pin) == 1
            and all(
                isinstance(part, str) and part for part in (*pin.keys(), *pin.values())
            )
            for pin in rules
        )
    )


def take_envelope(document: dict, folder: str) -> dict[str, Any]:
    """The provenance block, taken out of the document before anything is
    written, so what is committed is the `dmp` object alone.

    Absent or malformed is a refusal, not a default: a DMP whose rules
    versions are unknown cannot be checked against them, and guessing is
    worse than saying so.
    """
    envelope = document.pop(_ENVELOPE, None)
    if not isinstance(envelope, dict):
        raise SubmissionError(
            f"document carries no {_ENVELOPE!r} object, so the rules versions "
            f"it was built from are unknown. It was not rendered by a maDMP "
            f"document template."
        )
    # The folder comes from the submission service's URL and the project name
    # from the template that rendered the document. Comparing them is what
    # catches one project's document submitted through another's service.
    if envelope.get("project") != folder:
        raise SubmissionError(
            f"document was generated for project {envelope.get('project')!r}, "
            f"submitted to {folder!r}"
        )
    if (
        not isinstance(envelope.get("template_version"), str)
        or not envelope["template_version"]
    ):
        raise SubmissionError(f"{_ENVELOPE}.template_version is missing or empty")
    if not _pins_are_well_formed(envelope.get("rules")):
        raise SubmissionError(
            f"{_ENVELOPE}.rules is not a non-empty list of {{standard: version}} "
            f"mappings"
        )
    return envelope


def check(document: Any, envelope: dict[str, Any]) -> list[CheckResult]:
    """Check the document against the rules its envelope names. Raises with
    what to fix when it does not hold up, and otherwise hands back every
    result, which is what the verdict beside the DMP is written from.

    The versions come from the document, so what judges it is what it was
    built from, and a project whose pins moved since does not change the
    answer.
    """
    try:
        model = merge_rules(resolve_pins(envelope["rules"], RULES_DIR))
    except ProblemsError as err:
        raise QualityControlError(
            f"the rules this document names cannot be loaded, {err}"
        ) from err

    results = run_qc(model, document)
    if not has_failures(results):
        return results

    violations = [r for r in results if r.status == "fail"]
    spelled = "\n".join(f"  {r.message}" for r in violations[:_SPELLED_OUT])
    rest = len(violations) - _SPELLED_OUT
    versions = ", ".join(
        f"{name} {version}" for name, version in model.standard_versions
    )
    raise QualityControlError(
        f"quality control failed, {len(violations)} violation(s) against "
        f"{versions}:\n{spelled}" + (f"\n  and {rest} more" if rest > 0 else "")
    )


def verdict(results: list[CheckResult], envelope: dict[str, Any]) -> dict[str, Any]:
    """What is written beside a DMP to say it was checked, against what, and
    by what.

    The passing results are not kept, they say only that a field is a field.
    The warnings are, being the whole of what a document that passed still has
    to say. No timestamp: git dates the commit, and one here would change the
    bytes at every submission and kill the unchanged verdict.
    """
    counted = Counter(r.status for r in results)
    return {
        "verdict": "pass",
        "summary": {
            "total": len(results),
            **{status: counted.get(status, 0) for status in _STATUSES},
        },
        "rules": envelope["rules"],
        "engine": version("madmp-core"),
        "warnings": [
            {"instance_path": r.instance_path, "message": r.message}
            for r in results
            if r.status == "warning"
        ],
    }


def _bytes(document: Any) -> bytes:
    """One JSON file as it is committed. Trailing newline, so the registry
    holds text files git and every editor agree on."""
    return (
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode()


def _stored(entry: dict | None) -> bytes | None:
    """What the registry currently holds at a path, or None when nothing.

    (!!) GitHub inlines the content up to 1 MB only, and answers with an empty
    `content` and `encoding: "none"` above that. A DMP that large would never
    compare equal, so it would be committed again on every submission instead
    of reported unchanged.
    """
    if entry is None:
        return None
    return base64.b64decode(entry.get("content") or "")


def handle_submission(
    document: Any, folder: str, github: GitHubClient, config: SubmissionConfig
) -> dict[str, Any]:
    """Commit the DMP, its provenance and its verdict into
    ``projects/<folder>/template/`` of the registry, and rewrite ``dmp_id``,
    in the document it is given, to the DMP's raw URL.

    A document that does not hold up against the rules its envelope names is
    refused before any of that, so what the registry holds is what passed.

    The three files go in one commit, so nothing ever holds a DMP without the
    versions it was checked against or the verdict it got. Idempotent: a
    submission that says what is already there commits nothing. Returns a
    small summary DSW shows as the result."""
    if not _FOLDER_RE.match(folder or ""):
        raise SubmissionError(f"invalid project folder {folder!r}")
    if not isinstance(document, dict) or not isinstance(document.get("dmp"), dict):
        raise SubmissionError("document has no dmp object")
    envelope = take_envelope(document, folder)
    # Before anything is read or written: it needs no network, and it is the
    # answer the researcher is most likely waiting for.
    results = check(document, envelope)

    owner, repo = config.github_owner, config.registry_repo
    base = f"projects/{folder}"
    # The folder must have been laid out from madmp-core, otherwise dropping a
    # DMP would leave it in a folder nobody registered. Refuse rather than
    # create a half-folder.
    if github.get_file(owner, repo, f"{base}/template/.gitkeep") is None:
        raise SubmissionError(
            f"{base}/ is not initialized in {repo}, or not visible with this "
            f"token. Register the project from madmp-core first."
        )

    dmp_path = f"{base}/template/dmp_{folder}_template.json"
    meta_path = f"{base}/template/dmp_{folder}_template.meta.json"
    check_path = f"{base}/template/dmp_{folder}_template.check.json"
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{_BRANCH}/{dmp_path}"
    # The template set dmp_id to the DSW project URL as a placeholder, the
    # registry location is the DMP's real identifier.
    document["dmp"]["dmp_id"] = {"identifier": raw_url, "type": "url"}

    wanted = {
        dmp_path: _bytes(document),
        meta_path: _bytes(envelope),
        check_path: _bytes(verdict(results, envelope)),
    }
    current = {path: _stored(github.get_file(owner, repo, path)) for path in wanted}

    if current == wanted:
        action = "unchanged"
    else:
        action = "created" if current[dmp_path] is None else "updated"
        verb = "Add" if action == "created" else "Update"
        parent = github.branch_head(owner, repo, _BRANCH)
        if parent is None:
            raise SubmissionError(f"{repo} has no {_BRANCH} branch to commit to")
        # Named after the folder: every project commits into the same
        # repository, and `git log` shows the message before the path.
        github.commit_files(
            owner,
            repo,
            _BRANCH,
            wanted,
            f"{verb} DMP for {folder} (DSW submission)",
            parent,
        )

    return {
        "repository": f"https://github.com/{owner}/{repo}/tree/{_BRANCH}/{base}",
        "file": dmp_path,
        "metadata": meta_path,
        "check": check_path,
        "action": action,
        "folder": folder,
    }
