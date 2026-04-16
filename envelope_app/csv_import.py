from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any


def load_csv_records(path: Path) -> list[dict[str, Any]]:
    """
    Load rows from a CSV file. First row must be headers; each column name becomes a merge key
    (e.g. name -> {name}). Empty rows are skipped.
    """
    data = path.read_text(encoding="utf-8-sig")
    if not data.strip():
        return []

    sample = data[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel

    stream = io.StringIO(data)
    reader = csv.DictReader(stream, dialect=dialect)
    fieldnames = reader.fieldnames
    if not fieldnames:
        raise ValueError("CSV has no header row. Add a first row with column names.")

    cleaned_headers = [(h or "").strip() for h in fieldnames]
    if not any(cleaned_headers):
        raise ValueError("CSV header row is empty.")

    out: list[dict[str, Any]] = []
    for raw in reader:
        row: dict[str, Any] = {}
        for key, val in raw.items():
            k = (key or "").strip()
            if not k:
                continue
            if val is None:
                row[k] = ""
            elif isinstance(val, str):
                row[k] = val.strip()
            else:
                row[k] = val
        if any(str(v).strip() for v in row.values()):
            out.append(row)

    return out
