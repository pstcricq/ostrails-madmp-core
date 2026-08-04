"""Public API of the project configs.

``configs/projects/`` holds the project data — one self-contained YAML per
project, carrying its own facts, its rules pins and what the generated DSW
packages announce; this package holds the code that reads it: ``loader.py``
validates one file against ``config.schema.json``. The schema sits beside the
data it describes, so whoever is handed a config is handed a valid one.

It knows nothing of where the configs live: a caller passes a path, the way
``rules`` is passed paths and hands back a model.
"""

from configs.loader import ConfigFileError, load_config_file

__all__ = [
    "ConfigFileError",
    "load_config_file",
]
