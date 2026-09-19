"""Declarative study configuration and tabular output."""

from .config import ConfigError, StudyConfig, build_config, load_config
from .io import HAVE_PARQUET, TableWriteResult, read_rows, write_json, write_rows

__all__ = [
    "StudyConfig",
    "ConfigError",
    "load_config",
    "build_config",
    "write_rows",
    "read_rows",
    "write_json",
    "TableWriteResult",
    "HAVE_PARQUET",
]
