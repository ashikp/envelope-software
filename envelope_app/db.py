from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Batch:
    id: int
    name: str
    created_at: str
    row_count: int


@dataclass
class RecordRow:
    id: int
    batch_id: int
    payload: dict[str, Any]


@dataclass
class LabelTemplate:
    id: int
    name: str
    layout_json: str
    updated_at: str


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS batches (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS records (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
              payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS label_templates (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              layout_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_records_batch ON records(batch_id);

            CREATE TABLE IF NOT EXISTS app_settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def get_setting(self, key: str) -> str | None:
        cur = self._conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return None
        return str(row[0])

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def delete_setting(self, key: str) -> None:
        self._conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
        self._conn.commit()

    def create_batch_from_records(self, name: str, rows: list[dict[str, Any]]) -> int:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO batches (name, created_at) VALUES (?, ?)",
            (name, _utc_now()),
        )
        bid = int(cur.lastrowid)
        cur.executemany(
            "INSERT INTO records (batch_id, payload) VALUES (?, ?)",
            [(bid, json.dumps(r, ensure_ascii=False)) for r in rows],
        )
        self._conn.commit()
        return bid

    def list_batches(self) -> list[Batch]:
        cur = self._conn.execute(
            """
            SELECT b.id, b.name, b.created_at, COUNT(r.id) AS row_count
            FROM batches b
            LEFT JOIN records r ON r.batch_id = b.id
            GROUP BY b.id
            ORDER BY b.id DESC
            """
        )
        return [
            Batch(
                id=int(r["id"]),
                name=str(r["name"]),
                created_at=str(r["created_at"]),
                row_count=int(r["row_count"]),
            )
            for r in cur.fetchall()
        ]

    def get_records(self, batch_id: int) -> list[RecordRow]:
        cur = self._conn.execute(
            "SELECT id, batch_id, payload FROM records WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        )
        out: list[RecordRow] = []
        for r in cur.fetchall():
            payload = json.loads(r["payload"])
            if not isinstance(payload, dict):
                payload = {"value": payload}
            out.append(
                RecordRow(
                    id=int(r["id"]),
                    batch_id=int(r["batch_id"]),
                    payload=payload,
                )
            )
        return out

    def delete_batch(self, batch_id: int) -> None:
        self._conn.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        self._conn.commit()

    def upsert_template(self, name: str, layout_json: str) -> int:
        now = _utc_now()
        cur = self._conn.execute(
            "SELECT id FROM label_templates WHERE name = ?",
            (name,),
        )
        row = cur.fetchone()
        if row:
            self._conn.execute(
                "UPDATE label_templates SET layout_json = ?, updated_at = ? WHERE name = ?",
                (layout_json, now, name),
            )
            tid = int(row[0])
        else:
            c = self._conn.execute(
                "INSERT INTO label_templates (name, layout_json, updated_at) VALUES (?, ?, ?)",
                (name, layout_json, now),
            )
            tid = int(c.lastrowid)
        self._conn.commit()
        return tid

    def get_template(self, name: str) -> LabelTemplate | None:
        cur = self._conn.execute(
            "SELECT id, name, layout_json, updated_at FROM label_templates WHERE name = ?",
            (name,),
        )
        r = cur.fetchone()
        if not r:
            return None
        return LabelTemplate(
            id=int(r["id"]),
            name=str(r["name"]),
            layout_json=str(r["layout_json"]),
            updated_at=str(r["updated_at"]),
        )

    def delete_template(self, name: str) -> None:
        self._conn.execute("DELETE FROM label_templates WHERE name = ?", (name,))
        self._conn.commit()
