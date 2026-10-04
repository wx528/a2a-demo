"""V2 决策工作台 REST + SSE 路由。

模块导入时建立单例（store/broadcaster/backend/orchestrator）：
env（V2_DB、ROLE_AGENT_URLS）在导入时读取，测试通过重载本模块切换环境。
Orchestrator 只建一个，发言后端按任务分流：demo 任务走确定性脚本，真实任务走角色 Agent。
"""

import asyncio
import os
import re
import time
import uuid
from typing import Literal, Optional
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from web.v2 import demo
from web.v2.agents_client import ROLE_AGENTS, AgentSpeakerBackend, reload_urls
from web.v2.broadcaster import Broadcaster
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


class DemoOrRealBackend:
    """发言后端分流器：demo 任务用确定性脚本，真实任务调用角色 Agent。"""

    def __init__(self, broadcaster: Broadcaster):
        self._real = AgentSpeakerBackend(broadcaster)

    async def speak(self, task: V2Task, author: str, key: str) -> tuple[str, str, bool]:
        if task.demo:
            return demo.statement(key, task)
        return await self._real.speak(task, author, key)


store = V2Store(os.getenv("V2_DB", DEFAULT_DB))
store.init()  # TestClient 用例不触发 lifespan，表结构须在导入时就绪
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
    goal_text: str = Field(min_length=1)
    expected_outcome: str = ""
    constraints: list[str] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    advanced_mode: Literal["pipeline", "roundtable", "debate"] = "pipeline"
    advanced_rounds: int = Field(default=1, ge=1, le=3)


class StartRequest(BaseModel):
    constraints: Optional[list[str]] = None
    advanced_mode: Optional[Literal["pipeline", "roundtable", "debate"]] = None
    advanced_rounds: Optional[int] = Field(default=None, ge=1, le=3)


class DecisionRequest(BaseModel):
    option_id: str


class InterventionRequest(BaseModel):
    intent: Literal["追问", "补充条件", "调整方向"]
    text: str = Field(min_length=1)


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


# ============== 辅助 ==============


def _require_task(task_id: str) -> V2Task:
    task = store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


async def _probe_connections(task: V2Task) -> dict[str, str]:
    """角色连接状态：demo 任务固定 demo；真实任务探测 agent-card（2s 超时）。"""
    if task.demo:
        return {role: "demo" for role in ROLE_AGENTS}
    async with httpx.AsyncClient(trust_env=False, timeout=_PROBE_TIMEOUT) as client:

        async def probe(url: str) -> str:
            try:
                resp = await client.get(f"{url}{_PROBE_PATH}")
                return "up" if resp.status_code == 200 else "down"
            except Exception:
                return "down"

        keys = list(ROLE_AGENTS)
        states = await asyncio.gather(*(probe(ROLE_AGENTS[key]) for key in keys))
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
        task = await orchestrator.submit_decision(task_id, decision_id, req.option_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        task = await orchestrator.retry(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
            label = _AUTHOR_LABELS.get(t.author, t.author)
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
