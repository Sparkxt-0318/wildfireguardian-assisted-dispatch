"""Reading and writing sweep tables.

Parquet when pyarrow is installed, CSV otherwise.  The fallback is loud, not
silent: a caller who asked for ``.parquet`` and got ``.csv`` is told so, because
a pipeline that quietly changes format is a pipeline that loses data later.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Sequence

try:  # pragma: no cover - environment dependent
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAVE_PARQUET = True
except ImportError:  # pragma: no cover - environment dependent
    HAVE_PARQUET = False


class TableWriteResult:
    """Where a table actually landed, and in what format."""

    def __init__(self, path: Path, fmt: str, rows: int, fallback: bool) -> None:
        self.path = path
        self.format = fmt
        self.rows = rows
        self.fallback = fallback

    def describe(self) -> str:
        msg = f"wrote {self.rows} row(s) to {self.path} ({self.format})"
        if self.fallback:
            msg += ("  [pyarrow is not installed, so parquet was not available; "
                    "install the 'tables' extra for parquet output]")
        return msg


def write_rows(rows: Sequence[dict[str, Any]], path: str | Path) -> TableWriteResult:
    """Write flat records to parquet or CSV, inferred from the suffix."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("refusing to write an empty table")

    if path.suffix.lower() == ".parquet":
        if HAVE_PARQUET:
            pq.write_table(pa.Table.from_pylist([_flatten(r) for r in rows]), path)
            return TableWriteResult(path, "parquet", len(rows), fallback=False)
        path = path.with_suffix(".csv")
        return _write_csv(rows, path, fallback=True)
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(list(rows), indent=2, default=str))
        return TableWriteResult(path, "json", len(rows), fallback=False)
    return _write_csv(rows, path, fallback=False)


def _write_csv(rows: Sequence[dict[str, Any]], path: Path,
               *, fallback: bool) -> TableWriteResult:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(_flatten(row))
    return TableWriteResult(path, "csv", len(rows), fallback=fallback)


def read_rows(path: str | Path) -> list[dict[str, Any]]:
    """Read back a table written by :func:`write_rows`."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        if not HAVE_PARQUET:
            raise RuntimeError(
                f"{path} is parquet but pyarrow is not installed; "
                "install the 'tables' extra"
            )
        return pq.read_table(path).to_pylist()
    if suffix == ".json":
        return json.loads(path.read_text())
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    """Coerce values that parquet/CSV cannot hold directly."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (list, tuple, dict)):
            out[key] = json.dumps(value, default=str)
        else:
            out[key] = value
    return out


def write_json(payload: Any, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path


__all__ = ["write_rows", "read_rows", "write_json", "TableWriteResult",
           "HAVE_PARQUET"]
