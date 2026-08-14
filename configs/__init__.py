"""Public API of the project configs.

``configs/projects/`` holds the project data, one self-contained YAML per
project, carrying its own facts, its rules pins and what the generated DSW
packages announce. This package reads them.

``load_config_file()`` returns one config file, parsed and validated against
``config.schema.json`` and against the filename it sits at.
"""

from configs.loader import ConfigFileError, load_config_file

__all__ = [
    "ConfigFileError",
    "load_config_file",
]
