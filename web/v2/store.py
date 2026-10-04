import os
import sqlite3

from web.v2.models import V2Task


class V2Store:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def init(self):
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    status TEXT NOT NULL,
                    demo INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_task(self, task: V2Task):
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO tasks (id, data, created_at, status, demo) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    task.id,
                    task.model_dump_json(),
                    task.created_at,
                    task.status,
                    1 if task.demo else 0,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_task(self, task_id: str) -> V2Task | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT data FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return V2Task.model_validate_json(row[0]) if row else None
        finally:
            conn.close()

    def list_tasks(self) -> list[V2Task]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT data FROM tasks ORDER BY created_at DESC"
            ).fetchall()
            return [V2Task.model_validate_json(r[0]) for r in rows]
        finally:
            conn.close()

    def delete_task(self, task_id: str):
        conn = self._connect()
        try:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
        finally:
            conn.close()
