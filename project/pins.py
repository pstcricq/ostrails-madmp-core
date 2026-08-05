"""Where a project's declarations meet the resources they name.

A config says what it is built from as a list of pins, each naming one
standard and one version of it, and each naming exactly one file:
``<standard>/<version>.json`` under the rules standards. This module turns
those declarations into paths, and answers the one question that comes before
any use of them: does this project name resources that exist?

It opens nothing and validates no content. Whether a file is a well-formed
rules file is ``rules/``'s job, which it does on the way in. Here the question
is only *which* files, and whether they are there.

Neither data package can host this — each reads its own data and stops — and
no consumer owns it either: which versions a project is built from is a fact
about the project, true before anyone decides what to generate from it.

The pin *shape* is not re-checked: ``config.schema.json`` already requires a
list of single-key mappings whose values are strings, which is why the
unpacking below can be a one-liner. Pins reaching this module from anywhere
other than a validated config would need that check first.
"""

from __future__ import annotations

from pathlib import Path

from utils.errors import ProblemsError

Pin = dict[str, str]

#: A rules file is JSON. This module *builds* a path instead of being handed
#: one, so it is the only one here that has to spell the extension — it still
#: never opens what it names.
SUFFIX = ".json"


class UnresolvedPinsError(ProblemsError):
    """A project pins resources that are not there. No subject: the problems
    are about a *set* of pins, and one attempt lists them all."""

    noun = "unresolved pin"


def _is_one_component(part: str) -> bool:
    """Whether a pin part can be one path component and nothing else. A version
    is read from a file and then *built into* a path, so ``..`` or a separator
    in it would reach outside the resource tree.

    ``Path("..").name`` is ``".."``, not the empty string, so the dot names are
    named here rather than left to the round-trip below to catch."""
    return part not in ("", ".", "..") and part == Path(part).name


def _standards_in(root: Path) -> str:
    """What the tree offers, read off the disk. A directory counts only if it
    holds a versioned file, so a stray directory is not offered as a standard.

    A tree that is not there at all is its own answer: whoever called was
    pointed at the wrong directory, and saying so beats blaming the config for
    naming an unknown standard."""
    if not root.is_dir():
        return "nothing — no such directory"
    names = sorted(
        p.name for p in root.iterdir() if p.is_dir() and any(p.glob(f"*{SUFFIX}"))
    )
    return ", ".join(names) or "nothing"


def _versions_in(directory: Path) -> str:
    return ", ".join(sorted(p.stem for p in directory.glob(f"*{SUFFIX}"))) or "nothing"


def resolve_pins(pins: list[Pin], rules_dir: str | Path) -> list[Path]:
    """The rules files a config's ``rules:`` pins name, in the order the pins
    are written — the order the merge records tightenings in. Feeds
    :func:`project.merge.merge_rules`.

    Every pin is resolved, or every unresolved one is reported at once:
    resolution never stops at the first miss, because a config is fixed faster
    from the whole list, and the available names are read off the disk so a
    typo is corrected without going to look.
    """
    root = Path(rules_dir)
    paths, problems = [], []
    for pin in pins:
        ((name, version),) = pin.items()
        if not (_is_one_component(name) and _is_one_component(version)):
            problems.append(
                f"{name!r}: {version!r} — a pin names one directory and one "
                f"file, so neither part may be a path."
            )
            continue
        directory = root / name
        path = directory / f"{version}{SUFFIX}"
        if not directory.is_dir():
            problems.append(
                f"unknown standard {name!r}; {root} has {_standards_in(root)}."
            )
        elif not path.is_file():
            problems.append(
                f"standard {name}: unknown version {version!r}; it has "
                f"{_versions_in(directory)}."
            )
        else:
            paths.append(path)
    if problems:
        raise UnresolvedPinsError(problems)
    return paths
