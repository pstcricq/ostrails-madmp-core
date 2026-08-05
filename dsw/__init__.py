"""What turns a project into the packages DS Wizard consumes.

``rules/`` and ``configs/`` read and validate their own files, ``project/``
says what a project resolves to, and this package is the first that knows what
DSW *is*: a package identifier, an entity uuid, an event payload, a Jinja
document template.

Four kinds of module, each answering to a rule that can refuse an addition:

- ``uuids.py`` knows nothing at all — the standard library and the shape of a
  field path. It is the whole UUID convention, frozen: every DSW entity of
  every artifact takes its identity from here, which is what lets two
  generators reference each other's entities without sharing a table.
- ``common.py`` is what two modules here must answer *identically*, and would
  be a fault to disagree on: what a rules field becomes, in both generators,
  and where an artifact lands, between the generator that writes it and the
  publisher that reads it back. It opens no file and reaches no instance.
  Something one module alone uses is not common — it belongs in that module.
- ``generate_*.py`` are the only modules that write under ``build/``. Each
  owns one artifact and ignores the other.
- ``publish.py`` is the only module that talks to a DSW instance. It builds
  nothing and reads only what the generators already wrote, so a failed upload
  is never a question about the artifacts.

**The rule this package refuses an addition by:** a module here names
something that is DSW's own — an identifier, an entity, a payload field, an
endpoint. A module that would still make sense with DSW deleted belongs
upstream, in ``project/`` or in a data package.

Nothing is re-exported here. Inside the package, modules import each other by
name (``from dsw.common import field_kind``), so there is one way to reach a
thing rather than two.
"""
