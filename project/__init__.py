"""Public API of what a project resolves to.

``rules/`` and ``configs/`` each read and validate their own data, and stop
there. This package answers the question neither of them can: *this project,
resolved, is what?*

- ``pins.py`` turns the pins a config declares into the rules files they name,
  and reports the ones that are not there. It is the only place where a
  declaration is confronted with a resource tree;
- ``merge.py`` merges validated rules documents, base standard first, into the
  one typed :class:`~project.merge.Model` that DSW generation and quality
  control both read;
- ``assemble.py`` puts a config and its merged model together, in the one
  order that works, so that no two consumers assemble a project differently.

**The rule this package refuses an addition by:** a module here answers *"this
project, resolved, is what?"*, and knows no destination and no file format. It
may import a data package's façade — crossing them is its subject — but a
``json`` or ``yaml`` import here means a loader's job has leaked in, and a DSW
identifier or an output path means a generator's has.

Each module stands alone. Quality control on a submitted DMP resolves and
merges the pins recorded in the registry's ``meta.yaml`` without ever building
a :class:`~project.assemble.Project`, and the merge is tested on paths written
by hand. Nothing here calls anything else here; ``assemble.py`` is the only
module that knows the order.
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
