"""What several packages build on, and nothing else.

Unlike the other packages here, this one is not a subject: it is a place for
leaf modules that answer no question of their own. ``errors.py`` fixes the
shape every error in the repository takes; ``schema.py`` holds the JSON-Schema
plumbing ``rules/`` and ``configs/`` each validate their own data with. Both
depend on nothing but the standard library and ``jsonschema``, which is what
lets any package raise or validate without coupling to another.

**It therefore exports nothing.** A façade names a package's public API, and
there is no single one to name here: a caller imports the module it needs
(``from utils.errors import ProblemsError``), and that import says which piece
of plumbing is being reached for. Re-exporting would hide it.

**The rule this package refuses an addition by: two conditions, both
required.** A module here knows nothing of maDMP — no rules, no configs, no
project, no DSW, no registry, nothing this repository is *about* — **and** at
least two packages import it. The first alone is not enough, and that is the
point: a client for one destination is generic code with a single consumer, so
it belongs to that destination (``registry/`` carries its GitHub client,
``dsw/`` its DSW one). Being generic only makes a module eligible; being
shared is what earns it a place.
"""
