"""Run the quality control of one DMP: a document in, an envelope out.

    python -m quality_control.run \
        --pins  projects/glider/template/dmp_glider_template.meta.json \
        --dmp   projects/glider/template/dmp_glider_template.json \
        --json  qc_results.json

``--pins`` names the file carrying the rules versions to check against, in
the ``rules: [{standard: version}, ...]`` shape. Two files are written in that
shape and both are read here: the provenance file a submission commits beside
its DMP (JSON), and a project config (YAML).

Exit code 0 when the document has no real violation, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from project import RULES_DIR, merge_rules, resolve_pins
from quality_control.engine import STATUSES, envelope, run_qc
from utils.errors import ProblemsError


class PinsFileError(ProblemsError):
    """The file naming the rules versions cannot be read as such."""

    noun = "pins problem"


def read_pins(path: str | Path) -> list[dict[str, str]]:
    """The pins declared by one file, JSON or YAML by its suffix.

    Neither file is schema-validated on its way in, so the two ways it can
    fail before the pins are even readable are named here rather than
    surfacing as a bare KeyError or TypeError.
    """
    path = Path(path)
    try:
        text = path.read_text()
    except OSError as err:
        raise PinsFileError([f"cannot be read, {err.strerror or err}"], path) from err
    try:
        document = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as err:
        raise PinsFileError([f"does not parse, {err}"], path) from err

    if not isinstance(document, dict):
        raise PinsFileError(
            [
                (
                    "is not a mapping, so it carries no 'rules' key. Expected "
                    "the provenance file committed beside a DMP, or a project "
                    "config."
                )
            ],
            path,
        )
    if "rules" not in document:
        raise PinsFileError(
            [
                (
                    "has no 'rules' key, which is where the versions a DMP was "
                    "built from are written."
                )
            ],
            path,
        )
    return document["rules"]


def read_document(path: str | Path) -> Any:
    """One DMP file, parsed. Whatever it holds, the engine answers for it."""
    path = Path(path)
    try:
        return json.loads(Path(path).read_text())
    except OSError as err:
        raise PinsFileError([f"cannot be read, {err.strerror or err}"], path) from err
    except ValueError as err:
        raise PinsFileError([f"is not valid JSON, {err}"], path) from err


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pins",
        required=True,
        help="file carrying the rules versions to check against",
    )
    parser.add_argument("--dmp", required=True, help="DMP JSON to check")
    parser.add_argument("--json", required=True, help="results envelope to write")
    parser.add_argument("--rules-dir", default=str(RULES_DIR))
    args = parser.parse_args(argv)

    try:
        pins = read_pins(args.pins)
        document = read_document(args.dmp)
        model = merge_rules(resolve_pins(pins, args.rules_dir))
    except ProblemsError as err:  # unreadable pins, unresolved pins, or a bad set
        print(err, file=sys.stderr)
        return 1

    written = envelope(model, run_qc(model, document), args.dmp)
    output = Path(args.json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(written, indent=2) + "\n")

    summary = written["summary"]
    counts = ", ".join(f"{summary[status]} {status}" for status in STATUSES)
    print(
        f"{args.dmp}: {summary['total']} checks against "
        f"{' + '.join(written['standards'])}, {counts} -> "
        f"{written['verdict'].upper()} ({args.json})"
    )
    return 0 if written["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
