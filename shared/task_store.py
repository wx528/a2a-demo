"""
SQLite 任务存储：InMemoryTaskStore 的持久化实现（write-through + 重启加载）。

通过环境变量接入（见各 agent main.py）：
    TASK_DB=/data/tasks.db

继承 InMemoryTaskStore 的全部业务逻辑（上下文续聊、历史裁剪等），
仅在写路径上同步落盘，启动时全量加载回内存。
"""

import json
import os
import sqlite3
import threading
from typing import Optional

from .models import Message, Task
from .a2a_server import InMemoryTaskStore, TaskState


class SqliteTaskStore(InMemoryTaskStore):
    def __init__(self, db_path: str):
        super().__init__()
        db_dir = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = db_path
        # 独立的数据库写锁（不覆盖父类的 _lock；RLock 允许覆写方法内嵌套调用 _flush）
        self._db_lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                context_id TEXT,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )
            """
        )
        self._conn.commit()
        self._load_all()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load_all(self):
        for (row,) in self._conn.execute("SELECT data FROM tasks"):
            task = Task.model_validate(json.loads(row))
            self._tasks[task.id] = task

    def _flush(self, task: Task):
        # dump 与写入同锁执行，避免并发 flush 用旧快照覆盖新快照
        with self._db_lock:
            data = task.model_dump(mode="json", by_alias=True, exclude_none=True)
            self._conn.execute(
                """
                INSERT INTO tasks (id, context_id, data, updated_at)
                VALUES (?, ?, ?,
                        strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    context_id = excluded.context_id,
                    data = excluded.data,
                    updated_at = excluded.updated_at
                """,
                (task.id, task.context_id, json.dumps(data, ensure_ascii=False)),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # 写路径覆写：先走内存逻辑，再落盘
    # ------------------------------------------------------------------

    def close(self):
        """关闭数据库连接（服务停机时调用）。"""
        with self._db_lock:
            self._conn.close()

    def create(self, message: Message) -> Task:
        # super() 的内存变更与落盘在同一个 _db_lock 段内，保证写序一致
        with self._db_lock:
            task = super().create(message)
            self._flush(task)
            return task

    def append_user_message(self, task: Task, message: Message):
        with self._db_lock:
            super().append_user_message(task, message)
            self._flush(task)

    def update_status(self, task: Task, state: TaskState, text: Optional[str] = None):
        with self._db_lock:
            super().update_status(task, state, text)
            self._flush(task)

    def add_artifact(self, task: Task, name: str, text: str, media_type: str = "text/plain"):
        with self._db_lock:
            super().add_artifact(task, name, text, media_type)
            self._flush(task)
