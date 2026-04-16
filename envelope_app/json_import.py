from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_records(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict) and "rows" in data and isinstance(data["rows"], list):
        rows = data["rows"]
    elif isinstance(data, dict) and "records" in data and isinstance(data["records"], list):
        rows = data["records"]
    else:
        raise ValueError("JSON must be an array of objects, or an object with a 'rows' or 'records' array.")

    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            out.append({"value": row, "no": i + 1})
    return out
