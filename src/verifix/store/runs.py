from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class RunStore:
    """SQLite history of runs (one row per run, full report JSON kept) for comparison and later analysis."""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL, issue_id TEXT, decision TEXT,
            attempts INTEGER, tokens INTEGER, score REAL, report TEXT)""")

    def save(self, issue_id: str, decision: str, attempts: int, tokens: int, score: float, report_json: str) -> int:
        cur = self.db.execute("INSERT INTO runs (created, issue_id, decision, attempts, tokens, score, report) VALUES (?,?,?,?,?,?,?)",
                              (time.time(), issue_id, decision, attempts, tokens, score, report_json))
        self.db.commit()
        return int(cur.lastrowid or 0)

    def list(self, limit: int = 20) -> list[tuple]:
        return self.db.execute("SELECT id, created, issue_id, decision, attempts, tokens, score FROM runs ORDER BY id DESC LIMIT ?",
                               (limit,)).fetchall()

    def get(self, run_id: int) -> str | None:
        row = self.db.execute("SELECT report FROM runs WHERE id = ?", (run_id,)).fetchone()
        return row[0] if row else None
