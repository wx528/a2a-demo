"""
会议室持久化（SQLite）
提供会议、参与者、消息的增删改查，用于实现会话历史与会话列表。
"""

import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional


DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
)
DB_PATH = os.path.join(DB_DIR, "meetings.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构。"""
    conn = _get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                mode TEXT NOT NULL,
                max_rounds INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS participants (
                id TEXT NOT NULL,
                meeting_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                avatar TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'idle',
                PRIMARY KEY (id, meeting_id),
                FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                meeting_id TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                participant_name TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                FOREIGN KEY (meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_meeting_id ON messages(meeting_id);
            CREATE INDEX IF NOT EXISTS idx_participants_meeting_id ON participants(meeting_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_meeting(meeting: Dict):
    """保存或更新会议基本信息。"""
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO meetings (id, topic, mode, max_rounds, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                meeting["id"],
                meeting["topic"],
                meeting["mode"],
                meeting["max_rounds"],
                meeting["created_at"],
                meeting["status"],
            ),
        )
        # 覆盖参与者
        conn.execute("DELETE FROM participants WHERE meeting_id = ?", (meeting["id"],))
        for p in meeting.get("participants", []):
            conn.execute(
                """
                INSERT INTO participants (id, meeting_id, name, role, avatar, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    p["id"],
                    meeting["id"],
                    p["name"],
                    p["role"],
                    p["avatar"],
                    p["status"],
                ),
        )
        conn.commit()
    finally:
        conn.close()


def save_message(meeting_id: str, msg: Dict):
    """保存单条消息。"""
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO messages
            (id, meeting_id, participant_id, participant_name, role, content, timestamp, type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg["id"],
                meeting_id,
                msg["participant_id"],
                msg["participant_name"],
                msg["role"],
                msg["content"],
                msg["timestamp"],
                msg["type"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_participant_status(meeting_id: str, participant_id: str, status: str):
    """更新参与者状态。"""
    conn = _get_conn()
    try:
        conn.execute(
            """
            UPDATE participants SET status = ?
            WHERE meeting_id = ? AND id = ?
            """,
            (status, meeting_id, participant_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_meeting(meeting_id: str) -> Optional[Dict]:
    """根据 ID 获取完整会议（含参与者和消息）。"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
        if not row:
            return None

        meeting = dict(row)
        meeting["participants"] = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM participants WHERE meeting_id = ? ORDER BY rowid",
                (meeting_id,),
            )
        ]
        meeting["messages"] = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM messages WHERE meeting_id = ? ORDER BY rowid",
                (meeting_id,),
            )
        ]
        return meeting
    finally:
        conn.close()


def list_meetings() -> List[Dict]:
    """列出所有会议，按创建时间倒序。"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, topic, mode, max_rounds, created_at, status FROM meetings ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_meeting(meeting_id: str) -> bool:
    """删除会议及其关联数据。"""
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
