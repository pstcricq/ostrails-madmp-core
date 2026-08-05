"""What turns a project into the packages DS Wizard consumes.

``rules/`` and ``configs/`` read and validate their own files, ``project/``
says what a project resolves to, and this package is the first that knows what
DSW *is*: a package identifier, an entity uuid, an event payload, a Jinja
document template.

Three kinds of module, each answering to a rule that can refuse an addition:

- ``uuids.py`` knows nothing at all — the standard library and the shape of a
  field path. It is the whole UUID convention, frozen: every DSW entity of
  every artifact takes its identity from here, which is what lets two
  generators reference each other's entities without sharing a table.
- ``common.py`` is what the generators must answer *identically*. It never
  opens a file: loading is ``project/``'s job, writing is a generator's.
  Something used by a single generator is not common — it belongs in that
  generator.
- ``generate_*.py`` are the only modules that write under ``build/``. Each
  owns one artifact and ignores the other.

**The rule this package refuses an addition by:** a module here names
something that is DSW's own — an identifier, an entity, a payload field, an
endpoint. A module that would still make sense with DSW deleted belongs
upstream, in ``project/`` or in a data package.

Nothing is re-exported here. Inside the package, modules import each other by
name (``from dsw.common import field_kind``), so there is one way to reach a
thing rather than two.
"""
