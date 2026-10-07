"""V2 决策工作台 REST + SSE 路由。

模块导入时建立单例（store/broadcaster/backend/orchestrator）：
env（V2_DB、ROLE_AGENT_URLS）在导入时读取，测试通过重载本模块切换环境。
Orchestrator 只建一个，发言后端按任务分流：demo 任务走确定性脚本，真实任务走角色 Agent。
"""

import asyncio
import os
import re
import time
import unicodedata
import uuid
from typing import Literal, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from web.v2 import demo
from web.v2.agents_client import ROLE_AGENTS, AgentSpeakerBackend, reload_urls
from web.v2.broadcaster import Broadcaster
from web.v2.experts import Expert, V2ExpertStore, resolve_assignments
from web.v2.models import (
    STAGES,
    STAGE_LABELS,
    AcceptanceItem,
    ActionItem,
    Constraint,
    EvidenceItem,
    Material,
    OutcomeDoc,
    PathOption,
    Reason,
    SummaryGroups,
    V2Task,
)
from web.v2.orchestrator import Orchestrator
from web.v2.store import V2Store
from web.v2.util import sse_event

reload_urls()

router = APIRouter(prefix="/api/v2")

DEFAULT_DB = "data/v2_tasks.db"
DEFAULT_OUTCOME = "一份采用建议与试点计划"
_KEEPALIVE_SECONDS = 15
_ACTIVE_STATUSES = ("running", "waiting_confirmation")
_PROBE_TIMEOUT = 2.0
_PROBE_PATH = "/.well-known/agent-card.json"


_DEMO_TURN_DELAY = float(os.getenv("V2_DEMO_TURN_DELAY", "0.6"))


class DemoOrRealBackend:
    """发言后端分流器：demo 任务用确定性脚本，真实任务调用角色 Agent。"""

    def __init__(self, broadcaster: Broadcaster):
        self._real = AgentSpeakerBackend(broadcaster)

    async def speak(self, task: V2Task, author: str, key: str) -> tuple[str, str, bool]:
        if task.demo:
            # 演示发言按节奏推进：讨论逐条展开，pause/resume 也因此可从外部介入
            await asyncio.sleep(_DEMO_TURN_DELAY)
            return demo.statement(key, task)
        return await self._real.speak(task, author, key)


store = V2Store(os.getenv("V2_DB", DEFAULT_DB))
store.init()  # TestClient 用例不触发 lifespan，表结构须在导入时就绪
_EXPERT_STORE = V2ExpertStore(os.getenv("V2_DB", DEFAULT_DB))
_EXPERT_STORE.init()
broadcaster = Broadcaster()
backend = DemoOrRealBackend(broadcaster)
orchestrator = Orchestrator(store, backend, broadcaster)

_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    """创建后台任务并持有引用，避免被垃圾回收中断。"""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


# ============== 请求模型（风格照抄 CreateMeetingRequest） ==============


class CreateV2TaskRequest(BaseModel):
    goal_type: Literal["decision", "research", "compare", "review"] = "decision"
    goal_text: str = Field(min_length=1, max_length=300)
    expected_outcome: str = Field(default="", max_length=200)
    constraints: list[str] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    advanced_mode: Literal["pipeline", "roundtable", "debate"] = "pipeline"
    advanced_rounds: int = Field(default=2, ge=1, le=3)

    @field_validator("constraints")
    @classmethod
    def _constraints_length_limit(cls, value: list[str]) -> list[str]:
        for item in value:
            if len(item) > 200:
                raise ValueError("单条约束不超过 200 字")
        return value


class StartRequest(BaseModel):
    constraints: Optional[list[str]] = None
    advanced_mode: Optional[Literal["pipeline", "roundtable", "debate"]] = None
    advanced_rounds: Optional[int] = Field(default=None, ge=1, le=3)
    assignments: Optional[dict[str, str]] = None


class DecisionRequest(BaseModel):
    option_id: str


class InterventionRequest(BaseModel):
    intent: Literal["追问", "补充条件", "调整方向"]
    text: str = Field(min_length=1, max_length=2000)


class OutcomePatchRequest(BaseModel):
    # 注意：不含 label——label 只能经 outcome/confirm 接口修改
    conclusion: Optional[str] = None
    summary_groups: Optional[SummaryGroups] = None
    reasons: Optional[list[Reason]] = None
    path_comparison: Optional[list[PathOption]] = None
    evidence: Optional[list[EvidenceItem]] = None
    open_questions: Optional[list[str]] = None
    actions: Optional[list[ActionItem]] = None
    acceptance: Optional[list[AcceptanceItem]] = None


class CreateExpertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    url: str
    tags: list[str] = Field(default_factory=list, max_length=8)
    emoji: str = "🔌"

    @field_validator("tags")
    @classmethod
    def _tags_limit(cls, value: list[str]) -> list[str]:
        cleaned = [tag.strip() for tag in value if tag.strip()]
        for tag in cleaned:
            if len(tag) > 12:
                raise ValueError("单个标签不超过 12 字")
        return cleaned

    @field_validator("url")
    @classmethod
    def _url_scheme(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("地址必须以 http:// 或 https:// 开头")
        return value


class UpdateExpertRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    url: Optional[str] = None
    tags: Optional[list[str]] = Field(default=None, max_length=8)
    emoji: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name_clean(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = value.replace("\n", " ").strip()
        if not cleaned:
            raise ValueError("名称不能为空")
        return cleaned

    @field_validator("emoji")
    @classmethod
    def _emoji_clean(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        cleaned = "".join(
            ch for ch in value if not unicodedata.category(ch).startswith("C")
        ).strip()
        if len(cleaned) > 4:
            raise ValueError("emoji 不超过 4 个字符")
        return cleaned

    @field_validator("tags")
    @classmethod
    def _tags_limit(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return value
        cleaned = []
        for tag in value:
            tag = tag.replace("\n", " ").strip()
            if tag:
                cleaned.append(tag)
        for tag in cleaned:
            if len(tag) > 12:
                raise ValueError("单个标签不超过 12 字")
        return cleaned

    @field_validator("url")
    @classmethod
    def _url_scheme(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.replace("\n", " ").strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("地址必须以 http:// 或 https:// 开头")
        return value


# ============== 辅助 ==============


def _require_task(task_id: str) -> V2Task:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


def _probe_expert(url: str) -> tuple[bool, str]:
    """探活单个 Agent：GET agent-card（2s 超时），返回 (是否可达, 失败原因)。"""
    try:
        resp = httpx.get(f"{url}{_PROBE_PATH}", trust_env=False, timeout=_PROBE_TIMEOUT)
    except Exception as exc:
        # 只保留异常类型名，不回显底层 message（防内网拓扑泄漏）
        return False, type(exc).__name__
    return (True, "") if resp.status_code == 200 else (False, f"HTTP {resp.status_code}")


def _probe_card(url: str) -> tuple[bool, str, str]:
    """注册/更新前的探活 + 展示名：返回 (是否可达, 失败原因, card name)。

    探活经 _probe_expert（保留其可被测试 monkeypatch 的二元组签名），
    可达时再取 agent-card 的 name；整体只在工作线程内调用，不阻塞事件循环。
    """
    ok, reason = _probe_expert(url)
    if not ok:
        return False, reason, ""
    return True, "", _fetch_card_name(url)


async def _probe_label(url: str) -> str:
    """线程池并发探活并映射为 up/down/unknown（探测函数自身已兜底异常）。"""
    try:
        ok, _reason = await asyncio.to_thread(_probe_expert, url)
    except Exception:
        return "unknown"
    return "up" if ok else "down"


async def _probe_connections(task: V2Task) -> dict[str, str]:
    """角色连接状态：demo 任务固定 demo；真实任务探测 agent-card（2s 超时）。"""
    if task.demo:
        return {role: "demo" for role in ROLE_AGENTS}
    keys = list(ROLE_AGENTS)
    states = await asyncio.gather(*(_probe_label(ROLE_AGENTS[key]) for key in keys))
    return dict(zip(keys, states))


# ============== 任务路由 ==============


@router.post("/tasks")
async def create_task(req: CreateV2TaskRequest):
    if req.goal_type != "decision":
        raise HTTPException(
            status_code=422, detail="该目标类型本轮暂不支持，已为你锁定「做出决策」路径"
        )
    now = time.time()
    task = V2Task(
        id=uuid.uuid4().hex[:8],
        goal_text=req.goal_text,
        expected_outcome=req.expected_outcome.strip() or DEFAULT_OUTCOME,
        constraints=[Constraint(text=c) for c in req.constraints],
        materials=list(req.materials),
        advanced_mode=req.advanced_mode,
        advanced_rounds=req.advanced_rounds,
        demo=demo.demo_enabled(),
        created_at=now,
        updated_at=now,
    )
    # 创建即固化默认出场快照：无指派请求也保证运行期 author 一定能在快照中解析
    task.experts, task.assignments = resolve_assignments({}, _EXPERT_STORE)
    store.save_task(task)
    return task.public_dict()


@router.get("/tasks")
async def list_tasks():
    return [
        {
            "id": t.id,
            "goal_text": t.goal_text,
            "status": t.status,
            "current_stage": t.current_stage,
            "demo": t.demo,
            "outcome_summary": t.outcome.conclusion[:50] if t.outcome else "",
            "created_at": t.created_at,
        }
        for t in store.list_tasks()
    ]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = _require_task(task_id)
    data = task.public_dict()
    data["connections"] = await _probe_connections(task)
    return data


@router.post("/tasks/{task_id}/start")
async def start_task(task_id: str, req: StartRequest | None = None):
    task = _require_task(task_id)
    if task.status != "preparing":
        raise HTTPException(status_code=409, detail="计划已确认")
    if req is None:
        req = StartRequest()
    if req.assignments is not None:
        # 演示任务强制默认映射（防御）：外部指派不得改写演示剧本的出场角色
        requested = {} if task.demo else req.assignments
        task.experts, task.assignments = resolve_assignments(requested, _EXPERT_STORE)
    if req.constraints is not None:
        task.constraints = [Constraint(text=c) for c in req.constraints]
    if req.advanced_mode is not None:
        task.advanced_mode = req.advanced_mode
    if req.advanced_rounds is not None:
        task.advanced_rounds = req.advanced_rounds
    store.save_task(task)
    task.status = "running"
    store.save_task(task)
    broadcaster.publish(task_id, "status_change", {"status": "running"})
    _spawn(orchestrator.run_task(task_id))
    return task.public_dict()


@router.post("/tasks/{task_id}/decisions/{decision_id}")
async def submit_decision(task_id: str, decision_id: str, req: DecisionRequest):
    _require_task(task_id)
    try:
        # 只同步落盘决策并立即返回；发言与成果组装放后台，避免 HTTP 被阻塞数分钟
        task = orchestrator.resolve_decision(task_id, decision_id, req.option_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _spawn(orchestrator.continue_after_decision(task_id))
    return task.public_dict()


@router.post("/tasks/{task_id}/interventions")
async def submit_intervention(task_id: str, req: InterventionRequest):
    _require_task(task_id)
    try:
        ack = await orchestrator.submit_intervention(task_id, req.intent, req.text)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    fresh = store.get_task(task_id)
    return {**ack, "status": fresh.status if fresh else "unknown"}


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str):
    _require_task(task_id)
    orchestrator.pause(task_id)
    return store.get_task(task_id).public_dict()


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    _require_task(task_id)
    orchestrator.resume(task_id)
    task = store.get_task(task_id)
    has_open_gate = any(d.status == "open" for d in task.decisions)
    if task.status == "running" and not has_open_gate:
        _spawn(orchestrator.run_task(task_id))
    return task.public_dict()


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str):
    _require_task(task_id)
    try:
        # 同步重置状态并立即返回；续跑放后台
        task = orchestrator.retry_prepare(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _spawn(orchestrator.resume_driver(task_id))
    return task.public_dict()


@router.post("/tasks/{task_id}/end")
async def end_task(task_id: str):
    _require_task(task_id)
    try:
        task = await orchestrator.end_now(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return task.public_dict()


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    task = _require_task(task_id)
    # 先订阅再取快照，避免 init 之前发布的事件丢失
    queue = broadcaster.subscribe(task_id)

    async def event_stream():
        try:
            yield sse_event("init", task.public_dict())
            while True:
                try:
                    event, data = await asyncio.wait_for(
                        queue.get(), timeout=_KEEPALIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    fresh = store.get_task(task_id)
                    # 非活动任务空闲一个窗口即收流（EventSource 会自动重连拿到新 init）
                    if fresh is None or fresh.status not in _ACTIVE_STATUSES:
                        break
                    yield ": keepalive\n\n"
                else:
                    yield sse_event(event, data)
        finally:
            broadcaster.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ============== 成果路由 ==============


@router.get("/tasks/{task_id}/outcome")
async def get_outcome(task_id: str):
    task = _require_task(task_id)
    if task.outcome is None:
        raise HTTPException(status_code=404, detail="尚未生成成果")
    return task.outcome.model_dump()


@router.patch("/tasks/{task_id}/outcome")
async def patch_outcome(task_id: str, req: OutcomePatchRequest):
    task = _require_task(task_id)
    if task.status != "completed":
        raise HTTPException(status_code=409, detail="任务完成后才能编辑成果")
    if task.outcome is None:
        task.outcome = OutcomeDoc()
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(task.outcome, field, value)
    task.updated_at = time.time()
    store.save_task(task)
    return task.outcome.model_dump()


@router.post("/tasks/{task_id}/outcome/confirm")
async def confirm_outcome(task_id: str):
    task = _require_task(task_id)
    if task.status != "completed" or task.outcome is None:
        raise HTTPException(status_code=409, detail="任务完成后才能确认成果")
    task.outcome.label = "team_confirmed"
    task.updated_at = time.time()
    store.save_task(task)
    return task.outcome.model_dump()


# ============== 导出 ==============

_AUTHOR_LABELS = {
    "user": "你",
    "ada": "研究员 Ada",
    "turing": "方案设计师 Turing",
    "linus": "挑战者 Linus",
    "sage": "决策助手 Sage",
}

_MODE_LABELS = {"pipeline": "流水线", "roundtable": "圆桌", "debate": "辩论"}


def _author_label(task: V2Task, author: str) -> str:
    expert = task.expert_by_id(author)
    if expert is not None:
        return expert.name
    return _AUTHOR_LABELS.get(author, author)


def _export_markdown(task: V2Task) -> str:
    mode_text = _MODE_LABELS.get(task.advanced_mode, task.advanced_mode)
    created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.created_at))
    lines = [
        f"# 决策工作台记录：{task.goal_text}",
        "",
        f"- 状态：{task.status}",
        f"- 当前阶段：{STAGE_LABELS.get(task.current_stage, task.current_stage)}",
        f"- 模式：{mode_text}（{task.advanced_rounds} 轮）",
        "- 目标类型：做出决策",
        f"- 期望成果：{task.expected_outcome}",
        f"- 创建时间：{created}",
        "",
        "## 约束",
        "",
    ]
    for c in task.constraints:
        mark = "✓" if c.confirmed else "·"
        lines.append(f"- {mark} {c.text}")
    lines.append("")
    for stage in STAGES:
        stage_turns = [t for t in task.turns if t.stage == stage]
        if not stage_turns:
            continue
        lines += [f"### {STAGE_LABELS[stage]}"]
        lines.append("")
        for t in stage_turns:
            label = _author_label(task, t.author)
            lines.append(f"**{label} · {t.author}** #{t.seq}")
            lines.append("")
            if t.title:
                lines += [f"**{t.title}**", ""]
            lines += [t.body, ""]
    if task.decisions:
        lines += ["## 决策记录", ""]
        for d in task.decisions:
            chosen = next((o for o in d.options if o.id == d.chosen_id), None)
            result = f"已确认：{chosen.label}" if chosen else "待确认"
            lines.append(f"- {d.question} → {result}")
        lines.append("")
    if task.outcome is not None:
        o = task.outcome
        lines += ["## 成果", "", "### 结论", "", o.conclusion, "", "### 理由", ""]
        lines += [f"- **{r.title}**：{r.body}" for r in o.reasons]
        lines += ["", "### 方案对比", ""]
        for p in o.path_comparison:
            rec = "（推荐）" if p.recommended else ""
            lines.append(f"- **{p.name}**{rec}：{p.desc}")
            lines += [f"  - 优：{x}" for x in p.pros]
            lines += [f"  - 劣：{x}" for x in p.cons]
            if p.fit:
                lines.append(f"  - 适用：{p.fit}")
        lines += ["", "### 依据回看", ""]
        lines += [f"- #{e.seq_ref} {e.author}：{e.quote}" for e in o.evidence]
        lines += ["", "### 未解决问题", ""]
        lines += [f"- {q}" for q in o.open_questions]
        lines += ["", "### 行动项", ""]
        lines += [f"- {a.title}（{a.assignee}，{a.due}）：{a.detail}" for a in o.actions]
        lines += ["", "### 验收条件", ""]
        lines += [f"- {a.title}：{a.detail}" for a in o.acceptance]
        lines.append("")
    if task.demo:
        lines += ["> 本文包含演示模式生成的确定性内容", ""]
    return "\n".join(lines)


@router.get("/tasks/{task_id}/export")
async def export_task(task_id: str):
    task = _require_task(task_id)
    md = _export_markdown(task)
    # HTTP 头只允许 latin-1：ASCII 兜底名 + RFC 5987 filename* 保留原始中文名
    safe_goal = re.sub(r"[^\w\-.]+", "_", task.goal_text, flags=re.ASCII)[:40] or "task"
    utf8_goal = quote(f"{task.goal_text}.md", safe="")
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_goal}.md"; filename*=UTF-8\'\'{utf8_goal}'
            )
        },
    )


# ============== 专家路由 ==============


def _fetch_card_name(url: str) -> str:
    """从 agent-card 的 name 字段取展示名（≤40 字，解析失败不阻塞注册）。"""
    try:
        resp = httpx.get(f"{url}{_PROBE_PATH}", trust_env=False, timeout=_PROBE_TIMEOUT)
        return str(resp.json().get("name") or "")[:40]
    except Exception:
        return ""


def _expert_error_status(message: str) -> int:
    """ValueError → 状态码：不可删除 → 409；不存在 → 404；其余（冲突/重复）→ 409。"""
    if "不可删除" in message:
        return 409
    if "不存在" in message or "not found" in message.lower():
        return 404
    return 409


@router.get("/experts")
async def list_experts(enabled_only: bool = False):
    experts = _EXPERT_STORE.list_experts(enabled_only)
    states = await asyncio.gather(*(_probe_label(e.url) for e in experts))
    return [{**e.model_dump(), "probe": state} for e, state in zip(experts, states)]


@router.post("/experts")
async def create_expert(req: CreateExpertRequest):
    ok, reason, card_name = await asyncio.to_thread(_probe_card, req.url)
    if not ok:
        raise HTTPException(status_code=422, detail=f"无法连通该地址：{reason}")
    expert = Expert(
        id=uuid.uuid4().hex[:8],
        name=req.name,
        url=req.url,
        tags=req.tags,
        emoji=req.emoji,
        source="custom",
        card_name=card_name,
    )
    try:
        _EXPERT_STORE.create_expert(expert)
    except ValueError as exc:
        raise HTTPException(
            status_code=_expert_error_status(str(exc)), detail=str(exc)
        ) from exc
    return {**expert.model_dump(), "probe": "up"}


@router.patch("/experts/{expert_id}")
async def update_expert(expert_id: str, req: UpdateExpertRequest):
    fields = req.model_dump(exclude_none=True)
    if "url" in fields:
        ok, reason = await asyncio.to_thread(_probe_expert, fields["url"])
        if not ok:
            raise HTTPException(status_code=422, detail=f"无法连通该地址：{reason}")
    try:
        updated = _EXPERT_STORE.update_expert(expert_id, fields)
    except ValueError as exc:
        raise HTTPException(
            status_code=_expert_error_status(str(exc)), detail=str(exc)
        ) from exc
    return updated.model_dump()


@router.delete("/experts/{expert_id}")
async def delete_expert(expert_id: str):
    try:
        _EXPERT_STORE.delete_expert(expert_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=_expert_error_status(str(exc)), detail=str(exc)
        ) from exc
    return {"deleted": expert_id}
