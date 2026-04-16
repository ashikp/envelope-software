from __future__ import annotations

from pathlib import Path
from typing import Any

from envelope_app.csv_import import load_csv_records
from envelope_app.json_import import load_json_records


def load_records_file(path: Path) -> list[dict[str, Any]]:
    """Load mailing list from CSV (default) or JSON."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_csv_records(path)
    if suffix == ".json":
        return load_json_records(path)
    raise ValueError(
        f"Unsupported extension {suffix!r}. Use a .csv file (recommended) or .json."
    )
