from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional


class SimulationDatabase:
    def __init__(self, db_path: str = "desktop_backend/simulations.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS simulations (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    current_step INTEGER NOT NULL DEFAULT 0,
                    total_steps INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    config_json TEXT NOT NULL,
                    result_path TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            conn.commit()

    def create(self, row: Dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO simulations (
                    run_id, status, progress, current_step, total_steps, message,
                    config_json, result_path, created_at, started_at, finished_at
                )
                VALUES (
                    :run_id, :status, :progress, :current_step, :total_steps, :message,
                    :config_json, :result_path, :created_at, :started_at, :finished_at
                )
                """,
                row,
            )
            conn.commit()

    def update(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = :{key}" for key in fields)
        fields["run_id"] = run_id
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE simulations SET {assignments} WHERE run_id = :run_id", fields)
            conn.commit()

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM simulations WHERE run_id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM simulations ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def encode_config(config: Dict[str, Any]) -> str:
        return json.dumps(config, ensure_ascii=False)

