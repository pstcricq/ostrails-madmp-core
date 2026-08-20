"""The webhook's logic, free of HTTP plumbing.

A document is checked against the rules its own provenance names before anything
is written, so a DMP that does not hold up never reaches the registry at all
and the researcher hears why while they are still in DSW. What the registry
holds is therefore what has passed, and it holds the verdict beside it.

Stateless: everything derives from the document, the folder and a small static
config. Nothing here creates a repository or any scaffolding, the folder and
its subdirectories are laid out beforehand, by ``registry/``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from project import RULES_DIR, merge_rules, resolve_pins
from quality_control import envelope, run_qc
from utils.errors import ProblemsError
from utils.github import GitHubClient

# A safe folder slug: no dots or slashes, so a submission can never escape
# projects/<folder>/ (path traversal) or name anything but a folder.
_FOLDER_RE = re.compile(r"^[a-z0-9-]{1,64}$")

# (!!) The registry's default branch, and part of every dmp_id this webhook
# writes. A dmp_id is the DMP's stable identifier, so moving the registry to
# another branch would leave every identifier ever issued pointing nowhere.
_BRANCH = "main"

# The key the document template renders beside ``dmp``, carrying the versions
# the document was built from.
_PROVENANCE = "metadata"


# How many violations a refusal spells out before counting the rest. DSW
# shows this message on the submission, not a report, and a document missing
# forty fields would push the beginning of it out of sight. The count above
# the list says how many there were, so a truncated list never passes for
# the whole of it.
_SPELLED_OUT = 20


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

    # Both required, neither defaulted: app.py refuses to build this without
    # them.
    github_owner: str  # account owning the registry repo
    registry_repo: str  # the mono-repo all projects live in


def _pins_are_well_formed(rules: Any) -> bool:
    """Whether ``rules`` is a non-empty list of one-key mappings of strings,
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


def take_provenance(document: dict, folder: str) -> dict[str, Any]:
    """The provenance block, taken out of the document before anything is
    written, so what is committed is the ``dmp`` object alone.

    Absent or malformed is a refusal, not a default: a DMP whose rules
    versions are unknown cannot be checked against them, and guessing is
    worse than saying so.
    """
    provenance = document.pop(_PROVENANCE, None)
    if not isinstance(provenance, dict):
        raise SubmissionError(
            f"document carries no {_PROVENANCE!r} object, so the rules versions "
            f"it was built from are unknown. It was not rendered by a maDMP "
            f"document template."
        )
    # The folder comes from the submission service's URL and the project name
    # from the template that rendered the document. Comparing them is what
    # catches one project's document submitted through another's service.
    if provenance.get("project") != folder:
        raise SubmissionError(
            f"document was generated for project {provenance.get('project')!r}, "
            f"submitted to {folder!r}"
        )
    if (
        not isinstance(provenance.get("template_version"), str)
        or not provenance["template_version"]
    ):
        raise SubmissionError(f"{_PROVENANCE}.template_version is missing or empty")
    if not _pins_are_well_formed(provenance.get("rules")):
        raise SubmissionError(
            f"{_PROVENANCE}.rules is not a non-empty list of {{standard: version}} "
            f"mappings"
        )
    return provenance


def _listed(rows: list[dict[str, Any]], head: str) -> list[str]:
    """One headed block of result messages, cut at ``_SPELLED_OUT``.

    The head names the whole count, and a cut list says so on its last line,
    so nobody reads the first twenty as the whole of what is wrong.
    """
    lines = [
        f"{head}, the first {_SPELLED_OUT}:" if len(rows) > _SPELLED_OUT else f"{head}:"
    ]
    lines += [f"  {row['message']}" for row in rows[:_SPELLED_OUT]]
    if len(rows) > _SPELLED_OUT:
        lines.append(f"  [...] {len(rows) - _SPELLED_OUT} more not shown.")
    return lines


def _counted(qc: dict[str, Any]) -> str:
    """The line that closes every message: what held up, and what was left
    empty."""
    return (
        f"{qc['summary']['pass']} checks passed, "
        f"{qc['summary']['missing']} optional fields left empty."
    )


def _refusal(qc: dict[str, Any]) -> str:
    """What a researcher is told when their document does not hold up.

    Plain text in blocks, the violations first because they are the only
    thing they have to act on, then the warnings, which the refusal is not
    about and which say so.
    """
    versions = ", ".join(f"{name} {v}" for name, v in qc["rules_versions"].items())
    lines = [f"Quality control failed against {versions}.", ""]
    lines += _listed(qc["fail"], f"{len(qc['fail'])} violation(s) to fix")
    if qc["warning"]:
        lines += [
            "",
            *_listed(
                qc["warning"], f"{len(qc['warning'])} warning(s), which do not block"
            ),
        ]
    return "\n".join([*lines, "", _counted(qc)])


def _outcome(qc: dict[str, Any]) -> str:
    """What a researcher is told when their document is committed.

    (!!) DSW renders none of this. Its client shows a submitted document as a
    badge and a link to the Location header, and reads the response body only
    on a failure. The line is written and carried anyway, for whatever else
    reads a submission, and so the day DSW does show it there is nothing to
    write.
    """
    if not qc["warning"]:
        return f"Submitted. {_counted(qc)}"
    lines = _listed(qc["warning"], f"Submitted with {len(qc['warning'])} warning(s)")
    return "\n".join([*lines, "", _counted(qc)])


def check(document: Any, provenance: dict[str, Any], dmp: str) -> dict[str, Any]:
    """Check the document against the rules its provenance names, and hand
    back the envelope saying what was found. ``dmp`` is the path the envelope
    names, where the DMP will land.

    Raises with what to fix when the document does not hold up, so nothing
    downstream ever sees a failing envelope.

    The versions come from the document, so what judges it is what it was
    built from, and a project whose pins moved since does not change the
    answer.
    """
    try:
        model = merge_rules(resolve_pins(provenance["rules"], RULES_DIR))
    except ProblemsError as err:
        raise QualityControlError(
            f"the rules this document names cannot be loaded, {err}"
        ) from err

    qc = envelope(model, run_qc(model, document), dmp)
    if qc["verdict"] == "fail":
        raise QualityControlError(_refusal(qc))
    return qc


def _bytes(document: Any) -> bytes:
    """One JSON file as it is committed. Trailing newline, so the registry
    holds text files git and every editor agree on."""
    return (
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode()


def handle_submission(
    document: Any, folder: str, github: GitHubClient, config: SubmissionConfig
) -> dict[str, Any]:
    """Commit the DMP, its provenance and its verdict into
    ``projects/<folder>/template/`` of the registry, and rewrite ``dmp_id``,
    in the document it is given, to the DMP's raw URL.

    A document that does not hold up against the rules its provenance names is
    refused before any of that, so what the registry holds is what passed.

    The three files go in one commit, so nothing ever holds a DMP without the
    versions it was checked against or the verdict it got. Idempotent: a
    submission that says what is already there commits nothing. Returns a
    small summary DSW shows as the result."""
    if not _FOLDER_RE.match(folder or ""):
        raise SubmissionError(f"invalid project folder {folder!r}")
    if not isinstance(document, dict) or not isinstance(document.get("dmp"), dict):
        raise SubmissionError("document has no dmp object")
    provenance = take_provenance(document, folder)

    owner, repo = config.github_owner, config.registry_repo
    base = f"projects/{folder}"
    dmp_path = f"{base}/template/dmp_{folder}_template.json"
    # Before anything is read or written: it needs no network, and it is the
    # answer the researcher is most likely waiting for.
    qc = check(document, provenance, dmp_path)

    # The folder must have been laid out from madmp-core, otherwise dropping a
    # DMP would leave it in a folder nobody registered. Refuse rather than
    # create a half-folder.
    if github.get_file(owner, repo, f"{base}/template/.gitkeep") is None:
        raise SubmissionError(
            f"{base}/ is not initialized in {repo}, or not visible with this "
            f"token. Register the project first."
        )

    meta_path = f"{base}/template/dmp_{folder}_template.meta.json"
    check_path = f"{base}/template/dmp_{folder}_template.check.json"
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{_BRANCH}/{dmp_path}"
    # The template set dmp_id to the DSW project URL as a placeholder, the
    # registry location is the DMP's real identifier.
    document["dmp"]["dmp_id"] = {"identifier": raw_url, "type": "url"}

    wanted = {
        dmp_path: _bytes(document),
        meta_path: _bytes(provenance),
        check_path: _bytes(qc),
    }
    current = {path: github.get_file(owner, repo, path) for path in wanted}

    if current == wanted:
        action = "unchanged"
    else:
        action = "created" if current[dmp_path] is None else "updated"
        verb = "Add" if action == "created" else "Update"
        parent = github.branch_head(owner, repo, _BRANCH)
        if parent is None:
            raise SubmissionError(f"{repo} has no {_BRANCH} branch to commit to")
        # Named after the folder: every project commits into the same
        # repository, and ``git log`` shows the message before the path.
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
        "message": _outcome(qc),
    }
