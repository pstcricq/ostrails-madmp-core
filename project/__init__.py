"""Public API of what a project resolves to.

The question a config and its rules answer together, this project, resolved,
is what?

- ``pins.py`` turns the pins a config declares into the rules files they name,
  and reports the ones that are not there
- ``merge.py`` merges validated rules documents, base standard first, into one
  typed ``Model``
- ``assemble.py`` puts a config and its merged model together, in the one
  order that works

Two conditions for a module to belong here: it answers "this project,
resolved, is what?", and it knows no destination and no file format. It may
import a data package's façade, but a ``json`` or ``yaml`` import means a
loader's job has leaked in, and a DSW identifier or an output path means a
generator's has.

``pins.py`` and ``merge.py`` do not call each other, ``assemble.py`` is the
only module that composes them.
"""

from project.assemble import Project, assemble_project
from project.merge import (
    Field,
    Model,
    RulesConflictError,
    RulesSetError,
    Tightening,
    merge_rules,
)
from project.pins import UnresolvedPinsError, resolve_pins

__all__ = [
    "Field",
    "Model",
    "Project",
    "RulesConflictError",
    "RulesSetError",
    "Tightening",
    "UnresolvedPinsError",
    "assemble_project",
    "merge_rules",
    "resolve_pins",
]
