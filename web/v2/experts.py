import os
import sqlite3
from typing import Literal

from pydantic import BaseModel

from web.v2.models import TaskExpert

PURPOSES: list[str] = ["research", "propose", "challenge", "synthesize"]
PURPOSE_LABELS: dict[str, str] = {
    "research": "研究",
    "propose": "方案",
    "challenge": "挑战",
    "synthesize": "权衡",
}
PURPOSE_DUTIES: dict[str, str] = {
    "research": "核实事实与不确定性",
    "propose": "提出可执行方案",
    "challenge": "检查风险与隐含假设",
    "synthesize": "整理权衡与建议",
}
PURPOSE_TAG_BY: dict[str, str] = {
    "research": "研究",
    "propose": "设计",
    "challenge": "挑战",
    "synthesize": "权衡",
}
DEFAULT_ASSIGNMENTS: dict[str, str] = {
    "research": "ada",
    "propose": "turing",
    "challenge": "linus",
    "synthesize": "sage",
}


class Expert(BaseModel):
    id: str
    name: str
    url: str
    tags: list[str] = []
    emoji: str = "🔌"
    source: Literal["builtin", "custom"] = "custom"
    enabled: bool = True
    card_name: str = ""


def _builtin_url(role: str, port: int) -> str:
    """内置专家地址：优先 ROLE_AGENT_URLS env（compose 用容器名），本地回退 127.0.0.1。

    与 agents_client.ROLE_AGENTS 保持同一 env 语义，避免注册表与实际可达地址漂移。
    """
    raw = os.getenv("ROLE_AGENT_URLS", "")
    for pair in raw.split(","):
        name, sep, url = pair.strip().partition("=")
        if sep and name.strip() == role and url.strip():
            return url.strip()
    return f"http://127.0.0.1:{port}"


def _builtin_experts() -> list[Expert]:
    return [
        Expert(id="ada", name="研究员 · Ada", url=_builtin_url("ada", 8011), tags=["研究"], emoji="🧬", source="builtin"),
        Expert(id="turing", name="方案设计师 · Turing", url=_builtin_url("turing", 8012), tags=["设计", "方案"], emoji="🧠", source="builtin"),
        Expert(id="linus", name="挑战者 · Linus", url=_builtin_url("linus", 8013), tags=["挑战"], emoji="⚡", source="builtin"),
        Expert(id="sage", name="决策助手 · Sage", url=_builtin_url("sage", 8014), tags=["权衡"], emoji="⚖️", source="builtin"),
    ]


BUILTIN_EXPERTS: list[Expert] = _builtin_experts()


class V2ExpertStore:
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
                CREATE TABLE IF NOT EXISTS experts (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            for expert in BUILTIN_EXPERTS:
                conn.execute(
                    "INSERT OR IGNORE INTO experts (id, data, enabled) VALUES (?, ?, ?)",
                    (expert.id, expert.model_dump_json(), 1 if expert.enabled else 0),
                )
            conn.commit()
        finally:
            conn.close()

    def list_experts(self, enabled_only: bool = False) -> list[Expert]:
        conn = self._connect()
        try:
            sql = "SELECT data FROM experts"
            if enabled_only:
                sql += " WHERE enabled = 1"
            rows = conn.execute(sql + " ORDER BY rowid").fetchall()
            return [Expert.model_validate_json(r[0]) for r in rows]
        finally:
            conn.close()

    def get_expert(self, expert_id: str) -> Expert | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT data FROM experts WHERE id = ?", (expert_id,)
            ).fetchone()
            return Expert.model_validate_json(row[0]) if row else None
        finally:
            conn.close()

    def create_expert(self, expert: Expert):
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO experts (id, data, enabled) VALUES (?, ?, ?)",
                (expert.id, expert.model_dump_json(), 1 if expert.enabled else 0),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"专家 id 已存在：{expert.id}")
        finally:
            conn.close()

    def update_expert(self, expert_id: str, fields: dict) -> Expert:
        existing = self.get_expert(expert_id)
        if existing is None:
            raise ValueError(f"专家不存在：{expert_id}")
        if "id" in fields:
            raise ValueError("专家 id 不可修改")
        if "source" in fields:
            if existing.source == "builtin":
                raise ValueError("内置专家身份不可变更")
            raise ValueError("source 不可修改")
        updated = Expert.model_validate({**existing.model_dump(), **fields})
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO experts (id, data, enabled) VALUES (?, ?, ?)",
                (updated.id, updated.model_dump_json(), 1 if updated.enabled else 0),
            )
            conn.commit()
        finally:
            conn.close()
        return updated

    def delete_expert(self, expert_id: str):
        existing = self.get_expert(expert_id)
        if existing is not None and existing.source == "builtin":
            raise ValueError("内置专家不可删除，可禁用")
        conn = self._connect()
        try:
            conn.execute("DELETE FROM experts WHERE id = ?", (expert_id,))
            conn.commit()
        finally:
            conn.close()


def resolve_assignments(
    requested: dict[str, str], store: V2ExpertStore
) -> tuple[list[TaskExpert], dict[str, str]]:
    """校验请求指派并固化出场快照（assignments + experts 一并返回）。

    purpose 非法/专家不存在或被禁用 → 该槽回退默认映射；同一专家不可占两槽，
    重复时保留先到槽位、后到槽位回退默认。快照含全部出场专家（按 PURPOSES 顺序去重），
    内置默认一律取自 store（编辑过的 url/tags 随之生效）。
    """
    catalog = {e.id: e for e in store.list_experts()}
    assignments: dict[str, str] = {}
    used: set[str] = set()
    for purpose in PURPOSES:
        expert_id = requested.get(purpose) or ""
        if expert_id not in catalog or not catalog[expert_id].enabled or expert_id in used:
            expert_id = DEFAULT_ASSIGNMENTS[purpose]
        used.add(expert_id)
        assignments[purpose] = expert_id
    snapshot: dict[str, TaskExpert] = {}
    for purpose in PURPOSES:
        expert = catalog[assignments[purpose]]
        snapshot.setdefault(
            expert.id,
            TaskExpert(
                id=expert.id,
                name=expert.name,
                url=expert.url,
                emoji=expert.emoji,
                purpose=purpose,
                source=expert.source,
            ),
        )
    return list(snapshot.values()), assignments
