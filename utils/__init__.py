"""What several packages build on, and nothing else.

A place for leaf modules that answer no question of their own. ``errors.py``
fixes the shape every error in the repository takes, ``schema.py`` holds the
JSON-Schema plumbing, ``github.py`` is the transport every call to GitHub goes
through. They depend on nothing but the standard library and ``jsonschema``.

The package exports nothing. A caller imports the module it needs, as in
``from utils.errors import ProblemsError``.

Two conditions, both required, for a module to belong here: it knows nothing
of maDMP, and at least two packages import it.
"""
