"""
A2A 多人会议室 Web 演示
FastAPI + SSE 实时推送 + React 前端
"""

import os
import re
import uuid
import asyncio
from datetime import datetime
from typing import Dict, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env
load_env()
from shared.a2a_client import A2AJSONRPCClient
from debate.personas import PERSONAS
from debate.run_debate import build_turn_message
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import generators
import turns
from web.v2.routes import router as v2_router, store as v2_store
from web.v2.util import ThinkFilter as _ThinkFilter, _PHASE_LINE, _phase_or_none, sse_event


WEB_PORT = int(os.getenv("PORT", 8080))
RESEARCH_AGENT_URL = os.getenv("RESEARCH_AGENT_URL", "http://research-agent:8001")
WRITING_AGENT_URL = os.getenv("WRITING_AGENT_URL", "http://writing-agent:8002")
DEBATE_AGENT_URL = os.getenv("DEBATE_AGENT_URL", "http://localhost:8003")

PERSONA_AVATARS = {
    "socrates": "🏛️", "hume": "🔍", "kant": "⚖️", "nietzsche": "⚡",
    "skeptic_engineer": "🛠️", "vc": "💰", "judge": "👨‍⚖️",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库并把历史会议加载到内存
    db.init_db()
    for meeting_row in db.list_meetings():
        meeting = db.get_meeting(meeting_row["id"])
        if meeting:
            meetings[meeting["id"]] = Meeting(**meeting)
    v2_store.init()
    yield


app = FastAPI(title="A2A Meeting Room", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v2_router)


# ============== 数据模型 ==============

class Participant(BaseModel):
    id: str
    name: str
    role: str  # "user" | "agent"
    avatar: str
    status: str = "idle"  # idle | thinking | speaking


class ChatMessage(BaseModel):
    id: str
    meeting_id: str
    participant_id: str
    participant_name: str
    role: str
    content: str
    timestamp: str
    type: str = "message"  # message | system | status


class Meeting(BaseModel):
    id: str
    topic: str
    mode: str = "pipeline"  # pipeline | roundtable | debate
    max_rounds: int = 1
    auto_play: bool = False  # 默认步进
    pro_persona: str = ""
    con_persona: str = ""
    inquiry_enabled: bool = True  # 辩论模式：是否附带观众质询
    turn_state: Dict = {}
    created_at: str
    participants: List[Participant]
    messages: List[ChatMessage]
    status: str = "active"


# ============== 内存存储 ==============

meetings: Dict[str, Meeting] = {}

AGENTS = {
    "moderator": {
        "name": "Moderator",
        "url": RESEARCH_AGENT_URL,
        "avatar": "🎤",
        "role_hint": (
            "你是一场技术讨论会的主持人。你需要控制会议节奏，决定谁下一个发言。"
            "回答必须简洁，只给出决定或简短说明，不要长篇大论。\n\n"
        ),
    },
    "research": {
        "name": "Research Agent",
        "url": RESEARCH_AGENT_URL,
        "avatar": "🔬",
        "role_hint": "",
    },
    "writing": {
        "name": "Writing Agent",
        "url": WRITING_AGENT_URL,
        "avatar": "✍️",
        "role_hint": "",
    },
    "review": {
        "name": "Review Agent",
        "url": WRITING_AGENT_URL,
        "avatar": "🧐",
        "role_hint": (
            "你是一名技术编辑。请审校提供的文章，"
            "列出 3-5 条具体改进建议，包括内容准确性、结构清晰度、可读性等方面。"
            "回答用中文。直接输出建议，不要输出思考过程。\n\n"
        ),
    },
    "code": {
        "name": "Code Agent",
        "url": RESEARCH_AGENT_URL,
        "avatar": "💻",
        "role_hint": (
            "你是一名资深工程师。请根据主题提供一个简洁的代码示例或命令行示例，"
            "帮助读者快速上手。代码要有注释，说明关键步骤。"
            "回答用中文。直接输出代码和说明，不要输出思考过程。\n\n"
        ),
    },
    "summary": {
        "name": "Summary Agent",
        "url": WRITING_AGENT_URL,
        "avatar": "📝",
        "role_hint": (
            "你是一名会议助理。请根据整个会议讨论内容，"
            "用 3-5 条 bullet points 总结核心结论和下一步行动建议。"
            "回答用中文。直接输出总结，不要输出思考过程。\n\n"
        ),
    },
}


# ============== 辅助函数 ==============

def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def create_meeting(topic: str, mode: str = "pipeline", max_rounds: int = 1,
                   auto_play: bool = False, pro_persona: str = "socrates",
                   con_persona: str = "hume", inquiry_enabled: bool = True) -> Meeting:
    meeting_id = str(uuid.uuid4())[:8]

    if mode == "debate":
        pro = PERSONAS[pro_persona]
        con = PERSONAS[con_persona]
        participants = [
            Participant(id="user", name="你", role="user", avatar="👤"),
            Participant(id=pro["id"], name=pro["name"], role="agent",
                        avatar=PERSONA_AVATARS.get(pro["id"], "🗣️")),
            Participant(id=con["id"], name=con["name"], role="agent",
                        avatar=PERSONA_AVATARS.get(con["id"], "🗣️")),
            Participant(id="judge", name="裁判", role="agent", avatar=PERSONA_AVATARS["judge"]),
        ]
    else:
        participants = [
            Participant(id="user", name="你", role="user", avatar="👤"),
            Participant(id="research", name="Research Agent", role="agent", avatar="🔬"),
            Participant(id="writing", name="Writing Agent", role="agent", avatar="✍️"),
            Participant(id="review", name="Review Agent", role="agent", avatar="🧐"),
            Participant(id="code", name="Code Agent", role="agent", avatar="💻"),
            Participant(id="summary", name="Summary Agent", role="agent", avatar="📝"),
        ]
        if mode == "roundtable":
            participants.insert(1, Participant(id="moderator", name="Moderator", role="agent", avatar="🎤"))

    if mode == "roundtable":
        mode_text = f"圆桌讨论模式（{max_rounds} 轮）"
    elif mode == "debate":
        pro = PERSONAS[pro_persona]
        con = PERSONAS[con_persona]
        mode_text = f"辩论模式（{pro['name']} vs {con['name']}，{max_rounds} 轮）"
    else:
        mode_text = "流水线模式"

    meeting = Meeting(
        id=meeting_id,
        topic=topic,
        mode=mode,
        max_rounds=max_rounds,
        auto_play=auto_play,
        pro_persona=pro_persona if mode == "debate" else "",
        con_persona=con_persona if mode == "debate" else "",
        inquiry_enabled=inquiry_enabled,
        created_at=now(),
        participants=participants,
        messages=[
            ChatMessage(
                id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                participant_id="system",
                participant_name="系统",
                role="system",
                content=f"会议室已创建，主题：{topic}，模式：{mode_text}",
                timestamp=now(),
                type="system",
            )
        ],
    )
    meetings[meeting_id] = meeting
    db.save_meeting(meeting.model_dump())
    return meeting


def add_message(meeting_id: str, participant_id: str, content: str, msg_type: str = "message") -> ChatMessage:
    meeting = meetings[meeting_id]
    participant = next((p for p in meeting.participants if p.id == participant_id), None)
    name = participant.name if participant else participant_id
    role = participant.role if participant else "system"

    msg = ChatMessage(
        id=str(uuid.uuid4()),
        meeting_id=meeting_id,
        participant_id=participant_id,
        participant_name=name,
        role=role,
        content=content,
        timestamp=now(),
        type=msg_type,
    )
    meeting.messages.append(msg)
    db.save_message(meeting_id, msg.model_dump())
    return msg


def update_participant_status(meeting_id: str, participant_id: str, status: str):
    meeting = meetings[meeting_id]
    for p in meeting.participants:
        if p.id == participant_id:
            p.status = status
    db.update_participant_status(meeting_id, participant_id, status)


# ============== Agent 调用 ==============


async def call_agent(agent_key: str, input_text: str) -> str:
    """通过 A2A JSON-RPC 端点调用远端 Agent。"""
    agent = AGENTS[agent_key]
    full_input = f"{agent.get('role_hint', '')}{input_text}"

    client = A2AJSONRPCClient(agent["url"])
    try:
        task = await client.send_message(full_input)
    except Exception as e:
        return f"{agent['name']} 调用失败：{e}"

    artifacts = task.get("artifacts") or []
    if artifacts:
        for part in artifacts[0].get("parts", []):
            if part.get("text"):
                return part["text"].split("</think>")[-1].strip()
    return f"{agent['name']} 没有返回可用结果。"


async def call_agent_stream(agent_key: str, input_text: str):
    """流式调用远端 Agent，逐个 yield 文本增量；失败时 yield 单条错误文本。"""
    agent = AGENTS[agent_key]
    full_input = f"{agent.get('role_hint', '')}{input_text}"
    client = A2AJSONRPCClient(agent["url"])
    try:
        async for delta in client.stream_deltas(full_input):
            yield delta
    except Exception as e:
        yield f"{agent['name']} 调用失败：{e}"


async def run_agent_step(meeting_id: str, agent_key: str, input_text: str, context: str = ""):
    """运行单个 agent 步骤，带上完整会议上下文；发言流式推送。"""
    agent = AGENTS[agent_key]

    update_participant_status(meeting_id, agent_key, "thinking")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "thinking"})

    await asyncio.sleep(0.5)

    # 把完整上下文拼接到 prompt 中
    if context:
        full_input = (
            f"以下是会议室里已经讨论过的内容，请结合这些上下文发言。\n\n"
            f"===== 会议上下文 =====\n{context}\n===== 上下文结束 =====\n\n"
            f"现在请你作为 {agent['name']} 发言：\n\n{input_text}"
        )
    else:
        full_input = input_text

    think = _ThinkFilter()
    parts: List[str] = []
    spoke = False
    try:
        async for delta in call_agent_stream(agent_key, full_input):
            parts.append(delta)
            phase = _phase_or_none(delta)
            if phase:
                yield sse_event("agent_phase", {"participant_id": agent_key, "phase": phase})
                continue
            visible = think.feed(delta)
            if visible:
                if not spoke:
                    spoke = True
                    update_participant_status(meeting_id, agent_key, "speaking")
                    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "speaking"})
                yield sse_event("message_delta", {"participant_id": agent_key, "delta": visible})
    except Exception as e:
        if not spoke:
            result = f"{agent['name']} 调用失败：{e}"
            msg = add_message(meeting_id, agent_key, result)
            yield sse_event("message", msg.model_dump())
            update_participant_status(meeting_id, agent_key, "idle")
            yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "idle"})
            return

    result = _PHASE_LINE.sub("", "".join(parts)).split("</think>")[-1].strip()
    if not result:
        result = f"{agent['name']} 没有返回可用结果。"

    update_participant_status(meeting_id, agent_key, "speaking")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "speaking"})

    msg = add_message(meeting_id, agent_key, result)
    yield sse_event("message", msg.model_dump())

    update_participant_status(meeting_id, agent_key, "idle")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "idle"})


def build_meeting_context(meeting_id: str, max_chars_per_msg: int = 1500) -> str:
    """构建会议上下文，供 agent 参考"""
    meeting = meetings[meeting_id]
    context_lines = []
    for m in meeting.messages:
        if m.type == "message":
            content = m.content
            if len(content) > max_chars_per_msg:
                content = content[:max_chars_per_msg] + "...（内容已截断）"
            context_lines.append(f"{m.participant_name}：{content}")
    return "\n\n".join(context_lines)


def _side_argument(meeting, side: str) -> str:
    """取某一方最近一次发言（辩论上下文用）。"""
    pid = meeting.pro_persona if side == "pro" else meeting.con_persona
    for m in reversed(meeting.messages):
        if m.participant_id == pid and m.type == "message":
            return m.content[:2000]
    return ""


def _pending_inquiry(meeting) -> str:
    """自上一位 agent 发言后累积的用户消息（观众质询，最多取最近 2 条）。"""
    texts = []
    for m in meeting.messages:
        if m.participant_id == "user" and m.type == "message":
            texts.append(m.content)
        elif m.participant_id in (meeting.pro_persona, meeting.con_persona, "judge"):
            texts = []
    return "\n".join(texts[-2:])


async def call_debate_agent(message_text: str) -> str:
    client = A2AJSONRPCClient(DEBATE_AGENT_URL)
    try:
        task = await client.send_message(message_text)
    except Exception as e:
        return f"辩论 Agent 调用失败：{e}"
    for part in (task.get("artifacts") or [{}])[0].get("parts", []):
        if part.get("text"):
            return part["text"].split("</think>")[-1].strip()
    return "辩论 Agent 没有返回可用结果。"


async def call_debate_agent_stream(message_text: str):
    """流式调用辩论 Agent；失败时 yield 单条错误文本。"""
    client = A2AJSONRPCClient(DEBATE_AGENT_URL)
    try:
        async for delta in client.stream_deltas(message_text):
            yield delta
    except Exception as e:
        yield f"辩论 Agent 调用失败：{e}"


def db_save_state(meeting_id: str, state: Dict):
    meetings[meeting_id].turn_state = state
    db.save_meeting(meetings[meeting_id].model_dump())


def _participant_preview(meeting, spec) -> Dict:
    if spec["kind"] == "judge":
        return {"participant_id": "judge", "name": "裁判", "avatar": PERSONA_AVATARS["judge"]}
    if spec["kind"] == "debate":
        pid = meeting.pro_persona if spec["key"] == "pro" else meeting.con_persona
        p = PERSONAS[pid]
        return {"participant_id": pid, "name": p["name"], "avatar": PERSONA_AVATARS.get(pid, "🗣️")}
    return {"participant_id": spec["key"], "name": AGENTS[spec["key"]]["name"],
            "avatar": AGENTS[spec["key"]]["avatar"]}


async def _run_classic_step(meeting_id: str, spec: dict, topic: str):
    """流水线/圆桌（含 fallback 保底步）的单轮执行，prompt 移植自旧 flow。"""
    meeting = meetings[meeting_id]
    kind, key, index = spec["kind"], spec["key"], spec["index"]

    if meeting.mode == "roundtable" and kind == "agent":
        seq = turns.build_sequence(meeting.mode, meeting.max_rounds)
        if index == 0:
            opening = (
                f"欢迎来到圆桌讨论会。今天我们要讨论的主题是：{topic}。"
                "请各位专家结合上下文发表观点，如果暂时无话可补充可以说 PASS。"
            )
            async for event in run_agent_step(meeting_id, "moderator", opening):
                yield event
            return
        if index == len(seq) - 1:
            context = build_meeting_context(meeting_id, max_chars_per_msg=1500)
            closing_prompt = (
                f"你是主持人。会议主题：{topic}。\n\n"
                f"当前讨论上下文：\n{context}\n\n"
                f"请对本次圆桌讨论做简短总结。"
            )
            async for event in run_agent_step(meeting_id, "moderator", closing_prompt):
                yield event
            return

        r = (index - 1) // len(turns.ROUNDTABLE_AGENTS)
        off = (index - 1) % len(turns.ROUNDTABLE_AGENTS)
        agent_key = turns.ROUNDTABLE_AGENTS[off]
        context = build_meeting_context(meeting_id, max_chars_per_msg=1500)
        force_speak = r == 0 and agent_key in ["research", "writing"]
        agent_prompt = (
            f"你是 {AGENTS[agent_key]['name']}。会议主题：{topic}。\n\n"
            f"当前讨论上下文：\n{context}\n\n"
        )
        if force_speak:
            agent_prompt += "本轮请你必须发言，请结合主题和上下文发表观点，不要重复已有内容。"
        else:
            agent_prompt += (
                "主持人邀请你发言。请你判断是否有新的观点或补充。"
                "如果有，请直接发表观点；如果确实没有新内容，请只回复 PASS。"
                "不要重复之前已经说过的内容。"
            )

        update_participant_status(meeting_id, agent_key, "thinking")
        yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "thinking"})
        await asyncio.sleep(0.3)

        think = _ThinkFilter()
        parts: List[str] = []
        try:
            async for delta in call_agent_stream(agent_key, agent_prompt):
                parts.append(delta)
                phase = _phase_or_none(delta)
                if phase:
                    yield sse_event("agent_phase", {"participant_id": agent_key, "phase": phase})
                    continue
                visible = think.feed(delta)
                if visible:
                    yield sse_event("message_delta", {"participant_id": agent_key, "delta": visible})
        except Exception:
            pass  # 已累计的 parts 走正常落库路径；无增量时退化为占位文案

        response = _PHASE_LINE.sub("", "".join(parts)).split("</think>")[-1].strip()
        if not response:
            response = f"{AGENTS[agent_key]['name']} 没有返回可用结果。"

        if response.strip().upper().startswith("PASS"):
            yield sse_event("message_abort", {"participant_id": agent_key})
            msg = add_message(
                meeting_id, "system",
                f"{AGENTS[agent_key]['name']} 选择本轮 PASS", msg_type="pass",
            )
            yield sse_event("system", {"meeting_id": meeting_id, "content": msg.content})
            update_participant_status(meeting_id, agent_key, "idle")
            yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "idle"})
            return

        update_participant_status(meeting_id, agent_key, "speaking")
        yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "speaking"})
        msg = add_message(meeting_id, agent_key, response)
        yield sse_event("message", msg.model_dump())
        update_participant_status(meeting_id, agent_key, "idle")
        yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "idle"})
        return

    inputs = {
        "research": f"请研究这个主题：{topic}",
        "writing": f"主题：{topic}\n\n请基于会议上下文和主题写一篇文章。",
        "review": f"主题：{topic}\n\n请审校 Writing Agent 的文章，给出改进建议。",
        "code": f"主题：{topic}\n\n请提供一个简洁的代码示例或命令行示例。",
        "summary": f"主题：{topic}\n\n请总结整个会议的核心结论和下一步建议。",
    }
    context = build_meeting_context(meeting_id) if key != "research" else ""
    async for event in run_agent_step(meeting_id, key, inputs[key], context):
        yield event


async def _run_debate_step(meeting_id: str, spec: dict):
    meeting = meetings[meeting_id]
    if spec["kind"] == "judge":
        pid, persona, stance = "judge", None, "裁判"
        opponent = "\n\n---\n\n".join(
            f"{m.participant_name}：{m.content[:2000]}"
            for m in meeting.messages
            if m.participant_id in (meeting.pro_persona, meeting.con_persona)
        )
    else:
        side = spec["key"]
        pid = meeting.pro_persona if side == "pro" else meeting.con_persona
        persona = PERSONAS[pid]
        stance = "正方" if side == "pro" else "反方"
        opponent = _side_argument(meeting, "con" if side == "pro" else "pro")

    update_participant_status(meeting_id, pid, "thinking")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": pid, "status": "thinking"})

    if persona is not None:
        msg_text = build_turn_message(meeting.topic, persona, stance, opponent)
    else:
        msg_text = (
            f"[辩题/MOTION] {meeting.topic}\n"
            f"[角色/PERSONA] 裁判（中立评审，逐条核对论据与引用）\n"
            f"[立场/STANCE] 裁判\n"
            f"[对手论点/OPPONENT_ARGUMENTS]\n{opponent}"
        )
    inquiry = _pending_inquiry(meeting)
    if inquiry and meeting.inquiry_enabled and spec["kind"] != "judge":
        msg_text += f"\n[观众质询/INQUIRY]\n{inquiry}"

    think = _ThinkFilter()
    parts: List[str] = []
    spoke = False
    try:
        async for delta in call_debate_agent_stream(msg_text):
            parts.append(delta)
            phase = _phase_or_none(delta)
            if phase:
                yield sse_event("agent_phase", {"participant_id": pid, "phase": phase})
                continue
            visible = think.feed(delta)
            if visible:
                if not spoke:
                    spoke = True
                    update_participant_status(meeting_id, pid, "speaking")
                    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": pid, "status": "speaking"})
                yield sse_event("message_delta", {"participant_id": pid, "delta": visible})
    except Exception:
        pass  # 已累计文本走正常落库路径

    result = _PHASE_LINE.sub("", "".join(parts)).split("</think>")[-1].strip()
    if not result:
        result = await call_debate_agent(msg_text)

    update_participant_status(meeting_id, pid, "speaking")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": pid, "status": "speaking"})

    msg_type = "judge" if spec["kind"] == "judge" else "message"
    msg = add_message(meeting_id, pid, result, msg_type=msg_type)
    yield sse_event("message", msg.model_dump())

    update_participant_status(meeting_id, pid, "idle")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": pid, "status": "idle"})


async def run_turn(meeting_id: str):
    """执行恰好一轮发言，产出该轮 SSE 事件并以 turn_done 收尾。"""
    meeting = meetings[meeting_id]
    spec, new_state = turns.next_turn(meeting)
    if spec is None:
        yield sse_event("turn_done", {
            "meeting_id": meeting_id, "done": True, "next": None,
            "seq_index": int((meeting.turn_state or {}).get("seq_index", 0)),
        })
        return

    seq = turns.build_sequence(meeting.mode, meeting.max_rounds)
    steps = 1
    if spec["kind"] == "fallback" and turns.skip_fallback(seq, spec["index"], meeting):
        spec, new_state = turns.next_turn_with_index(meeting, spec["index"] + 1)
        steps = 2
        if spec is None:
            yield sse_event("turn_done", {
                "meeting_id": meeting_id, "done": True, "next": None,
                "seq_index": int(new_state.get("seq_index", 0)),
            })
            return
    meeting.turn_state = new_state
    db_save_state(meeting_id, meeting.turn_state)

    topic_override = meeting.turn_state.get("topic_override")
    topic = topic_override or meeting.topic

    if spec["kind"] in ("agent", "fallback"):
        async for event in _run_classic_step(meeting_id, spec, topic):
            yield event
    elif spec["kind"] in ("debate", "judge"):
        async for event in _run_debate_step(meeting_id, spec):
            yield event

    meeting.turn_state = turns.advance(meeting, steps)
    db_save_state(meeting_id, meeting.turn_state)

    nxt_spec, _ = turns.next_turn(meeting)
    nxt = _participant_preview(meeting, nxt_spec) if nxt_spec else None
    yield sse_event("turn_done", {
        "meeting_id": meeting_id, "done": nxt_spec is None, "next": nxt,
        "seq_index": int((meeting.turn_state or {}).get("seq_index", 0)),
    })


# ============== API 路由 ==============

def _ensure_meeting_loaded(meeting_id: str) -> bool:
    """如果会议不在内存中，尝试从数据库加载。"""
    if meeting_id in meetings:
        return True
    meeting_data = db.get_meeting(meeting_id)
    if meeting_data:
        meetings[meeting_id] = Meeting(**meeting_data)
        return True
    return False


DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
ASSETS_DIR = os.path.join(DIST_DIR, "assets")


@app.get("/")
async def serve_react():
    index_file = os.path.join(DIST_DIR, "index.html")
    if not os.path.exists(index_file):
        return HTMLResponse(
            "<h1>A2A 多人会议室</h1>"
            "<p>前端尚未构建。请运行：</p>"
            "<pre>cd web/frontend &amp;&amp; npm install &amp;&amp; npm run build</pre>",
        )
    return FileResponse(index_file)


if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/api/meetings")
async def list_meetings_api():
    """列出所有历史会议。"""
    return db.list_meetings()


@app.get("/api/meetings/{meeting_id}")
async def get_meeting(meeting_id: str):
    if not _ensure_meeting_loaded(meeting_id):
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meetings[meeting_id].model_dump()


def _export_markdown(meeting: Meeting) -> str:
    """把整场会议排版为 Markdown 文档。"""
    mode_text = {"pipeline": "流水线", "roundtable": "圆桌讨论", "debate": "辩论"}.get(
        meeting.mode, meeting.mode
    )
    lines = [
        f"# A2A 会议记录：{meeting.topic}",
        "",
        f"- 模式：{mode_text}" + (f"（{meeting.max_rounds} 轮）" if meeting.mode != "pipeline" else ""),
        f"- 创建时间：{meeting.created_at}",
        f"- 参与者：{'、'.join(p.name for p in meeting.participants)}",
        "",
        "---",
        "",
    ]
    for m in meeting.messages:
        if m.participant_id == "system":
            lines.append(f"> 📢 {m.content}")
        else:
            lines.append(f"**{m.participant_name}**（{m.timestamp}）")
            lines.append("")
            lines.append(m.content)
        lines.append("")
    return "\n".join(lines)


@app.get("/api/meetings/{meeting_id}/export")
async def export_meeting(meeting_id: str):
    """导出会议记录为 Markdown 附件下载。"""
    if not _ensure_meeting_loaded(meeting_id):
        raise HTTPException(status_code=404, detail="Meeting not found")
    meeting = meetings[meeting_id]
    md = _export_markdown(meeting)
    safe_topic = re.sub(r'[\\/:*?"<>|\s]+', "_", meeting.topic)[:40] or "meeting"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_topic}.md"',
        },
    )


@app.delete("/api/meetings/{meeting_id}")
async def delete_meeting_api(meeting_id: str):
    db.delete_meeting(meeting_id)
    meetings.pop(meeting_id, None)
    return {"deleted": True}


class CreateMeetingRequest(BaseModel):
    topic: str
    mode: str = "pipeline"  # pipeline | roundtable | debate
    max_rounds: int = 1
    auto_play: bool = False
    pro_persona: str = "socrates"
    con_persona: str = "hume"
    inquiry_enabled: bool = True


@app.post("/api/meetings")
async def create_meeting_api(req: CreateMeetingRequest):
    rounds_cap = 10 if req.mode == "roundtable" else 3
    max_rounds = (
        max(1, min(rounds_cap, req.max_rounds))
        if req.mode in ("roundtable", "debate") else 1
    )
    meeting = create_meeting(
        req.topic, mode=req.mode, max_rounds=max_rounds,
        auto_play=req.auto_play, pro_persona=req.pro_persona,
        con_persona=req.con_persona, inquiry_enabled=req.inquiry_enabled,
    )
    return meeting.model_dump()


@app.get("/api/personas")
async def list_personas():
    """辩论人格列表（不含裁判）。"""
    return [
        {"id": p["id"], "name": p["name"], "style": p["style"],
         "avatar": PERSONA_AVATARS.get(p["id"], "🗣️")}
        for p in PERSONAS.values() if p["id"] != "judge"
    ]


class SuggestTopicsRequest(BaseModel):
    count: int = 3
    seed: str = ""


@app.post("/api/topics/suggest")
async def suggest_topics_api(req: SuggestTopicsRequest):
    """LLM 生成候选议题（可围绕用户输入的关键词）。"""
    count = max(1, min(5, req.count))
    try:
        topics = await generators.suggest_topics(count, seed=req.seed)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 生成失败，请稍后重试：{e}")
    return {"topics": topics}


class PreviewViewpointsRequest(BaseModel):
    topic: str
    pro_persona: str
    con_persona: str


@app.post("/api/viewpoints/preview")
async def preview_viewpoints_api(req: PreviewViewpointsRequest):
    """LLM 并行生成正反双方开篇立论预览。"""
    if not req.topic.strip():
        raise HTTPException(status_code=422, detail="辩题不能为空")
    if req.pro_persona not in PERSONAS or req.con_persona not in PERSONAS:
        raise HTTPException(status_code=422, detail="人格不存在")
    pro, con = await generators.preview_viewpoints(
        req.topic.strip(), req.pro_persona, req.con_persona
    )
    return {"pro": pro, "con": con}


class SendMessageRequest(BaseModel):
    content: str


@app.post("/api/meetings/{meeting_id}/messages")
async def send_user_message(meeting_id: str, req: SendMessageRequest):
    if not _ensure_meeting_loaded(meeting_id):
        raise HTTPException(status_code=404, detail="Meeting not found")

    msg = add_message(meeting_id, "user", req.content)
    return msg.model_dump()


@app.get("/api/meetings/{meeting_id}/next-turn")
async def peek_next_turn(meeting_id: str):
    """预览下一位发言者（不执行）。"""
    if not _ensure_meeting_loaded(meeting_id):
        raise HTTPException(status_code=404, detail="Meeting not found")
    meeting = meetings[meeting_id]
    spec, _ = turns.next_turn(meeting)
    return {
        "done": spec is None,
        "next": _participant_preview(meeting, spec) if spec else None,
        "mode": meeting.mode,
        "auto_play": meeting.auto_play,
        "seq_index": int((meeting.turn_state or {}).get("seq_index", 0)),
    }


@app.post("/api/meetings/{meeting_id}/turns/next")
async def execute_next_turn(meeting_id: str):
    """执行恰好一轮发言（SSE 流式返回，turn_done 收尾）。"""
    if not _ensure_meeting_loaded(meeting_id):
        raise HTTPException(status_code=404, detail="Meeting not found")
    return StreamingResponse(run_turn(meeting_id), media_type="text/event-stream")


@app.get("/api/meetings/{meeting_id}/events")
async def meeting_events(meeting_id: str):
    """SSE 实时事件流：初始快照 + 心跳（流程执行走 turns/next）。"""
    if not _ensure_meeting_loaded(meeting_id):
        raise HTTPException(status_code=404, detail="Meeting not found")

    async def event_stream():
        meeting = meetings[meeting_id]
        yield sse_event("init", meeting.model_dump())
        while True:
            await asyncio.sleep(15)
            yield ": keepalive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
