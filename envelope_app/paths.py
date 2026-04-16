from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def app_data_dir() -> Path:
    loc = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if not loc:
        base = Path.home() / ".envelope_studio"
    else:
        base = Path(loc)
    base.mkdir(parents=True, exist_ok=True)
    return base


def database_path() -> Path:
    return app_data_dir() / "envelope_studio.sqlite3"


def template_images_dir() -> Path:
    """Imported images are copied here; paths in layout JSON are relative to app_data_dir()."""
    p = app_data_dir() / "template_images"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / relative
