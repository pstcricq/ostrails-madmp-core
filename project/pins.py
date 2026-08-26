"""Where a project's declarations meet the resources they name.

A config declares what it is built from as a list of pins, each naming one
standard and one version, and each naming exactly one file,
``<standard>/<version>.json`` under the rules standards. This module turns
those declarations into paths and answers one question, are the files there.

It opens nothing and validates no content, only which files are named and
whether they exist.

Pins are expected to be single-key mappings of strings, the shape a validated
config guarantees.
"""

from __future__ import annotations

from pathlib import Path

from utils.errors import ProblemsError

Pin = dict[str, str]

# A rules file is JSON. This module builds paths rather than being handed
# them, so it is the one that spells the extension.
SUFFIX = ".json"

# Where the standards live, this repository's own tree. This module turns a pin
# into a path under it, so it is the one that names it.
ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "rules" / "standards"


class UnresolvedPinsError(ProblemsError):
    """A project pins resources that are not there.

    No subject, the problems are about a set of pins rather than one file.
    """

    noun = "unresolved pin"


def _is_one_component(part: str) -> bool:
    """Whether a pin part can be one path component and nothing else.

    A pin part is read from a file and then built into a path, so ``..`` or a
    separator in it would reach outside the resource tree. The dot names are
    listed explicitly because ``Path("..").name`` is ``".."``, which the
    round-trip alone would let through.
    """
    return part not in ("", ".", "..") and part == Path(part).name


def _standards_in(root: Path) -> str:
    """What the tree offers, read off the disk, for an error message.

    A directory counts only if it holds a versioned file. A tree that is not
    there at all says so, rather than reporting every standard as unknown.
    """
    if not root.is_dir():
        return "nothing, no such directory"
    names = sorted(
        p.name for p in root.iterdir() if p.is_dir() and any(p.glob(f"*{SUFFIX}"))
    )
    return ", ".join(names) or "nothing"


def _versions_in(directory: Path) -> str:
    """The versions one standard directory offers, for an error message."""
    return ", ".join(sorted(p.stem for p in directory.glob(f"*{SUFFIX}"))) or "nothing"


def resolve_pins(pins: list[Pin], rules_dir: str | Path) -> list[Path]:
    """The rules files a config's ``rules:`` pins name, in the order written.

    Raises ``UnresolvedPinsError`` listing every pin that does not resolve,
    each with the names the tree does offer.
    """
    root = Path(rules_dir)
    paths, problems = [], []
    for pin in pins:
        ((name, version),) = pin.items()
        if not (_is_one_component(name) and _is_one_component(version)):
            problems.append(
                f"{name!r}: {version!r}, a pin names one directory and one "
                f"file, so neither part may be a path."
            )
            continue
        directory = root / name
        path = directory / f"{version}{SUFFIX}"
        if not directory.is_dir():
            problems.append(
                f"unknown standard {name!r}, {root} has {_standards_in(root)}."
            )
        elif not path.is_file():
            problems.append(
                f"standard {name}: unknown version {version!r}, it has "
                f"{_versions_in(directory)}."
            )
        else:
            paths.append(path)
    if problems:
        raise UnresolvedPinsError(problems)
    return paths
