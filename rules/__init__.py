"""Public API of the rules package.

``rules/standards/`` holds the maDMP rules as data, one JSON file per
standard per version. This package reads them.

``load_rules_file()`` returns one rules file, parsed and validated against
``rules.schema.json``, against the coherence constraints checked in
``loader.py``, and against the path the file sits at.

``field_children()`` returns a field node's declared child fields, its keys
that do not start with ``_``. It is exported so that anything walking a rules
tree splits metadata from children the same way the loader does.
"""

from rules.loader import RulesFileError, field_children, load_rules_file

__all__ = [
    "RulesFileError",
    "field_children",
    "load_rules_file",
]
