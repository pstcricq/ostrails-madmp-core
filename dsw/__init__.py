"""What turns a project into the packages DS Wizard consumes.

This is the first package that knows what DSW is: a package identifier, an
entity uuid, an event payload, a Jinja document template.

- ``uuids.py`` is the whole UUID convention, frozen, and knows nothing but the
  standard library and the shape of a field path
- ``common.py`` is what two modules here must answer identically, what a rules
  field becomes and where an artifact lands. It opens no file and reaches no
  instance
- ``generate_*.py`` are the only modules that write under ``build/``, each
  owning one artifact and ignoring the other
- ``publish.py`` is the only module that talks to a DSW instance, and builds
  nothing

One condition for a module to belong here: it names something that is DSW's
own, an identifier, an entity, a payload field, an endpoint.

Nothing is re-exported. Inside the package, modules import each other by name
(``from dsw.common import field_kind``), so there is one way to reach a thing
rather than two.
"""
