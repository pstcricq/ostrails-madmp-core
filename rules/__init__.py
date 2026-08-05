"""Public API of the rules data.

``rules/standards/`` holds the maDMP rules as data — one JSON file per
standard per version; this package holds the code that reads it:
``loader.py`` validates one file against ``rules.schema.json``, against the
coherence rules kept in Python for legible errors, and against the path it
sits at. The schema sits beside the data it describes, so whoever is handed a
rules file is handed a valid one.

Reading is all it does. Merging validated files into the typed model that DSW
generation and QC consume is the *application* of the rules, and belongs to
whoever applies them; which versions a given project pins is project data.
Neither is a fact about a rules file, so neither is admitted here. A caller
passes a path, and gets back a validated document.

``field_children`` is exported with it because the document's shape is this
package's fact: a field's children are its keys that do not start with ``_``.
Whoever walks a rules tree must split metadata from children exactly the way
the loader validated it, and one of them saying it differently is a drift
that nothing would catch.
"""

from rules.loader import RulesFileError, field_children, load_rules_file

__all__ = [
    "RulesFileError",
    "field_children",
    "load_rules_file",
]
