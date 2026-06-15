"""
A2A 多人会议室 Web 演示
FastAPI + SSE 实时推送 + React 前端
"""

import os
import uuid
import asyncio
import json
from datetime import datetime
from typing import Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import TextPart, Message, TaskSendParams
from shared.llm_client import call_llm


WEB_PORT = int(os.getenv("PORT", 8080))
RESEARCH_AGENT_URL = os.getenv("RESEARCH_AGENT_URL", "http://research-agent:8001")
WRITING_AGENT_URL = os.getenv("WRITING_AGENT_URL", "http://writing-agent:8002")


app = FastAPI(title="A2A Meeting Room")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    mode: str = "pipeline"  # pipeline | roundtable
    max_rounds: int = 1  # 圆桌讨论轮数
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
        "system_prompt": (
            "你是一场技术讨论会的主持人。你需要控制会议节奏，决定谁下一个发言。"
            "回答必须简洁，只给出决定或简短说明，不要长篇大论。"
        ),
    },
    "research": {
        "name": "Research Agent",
        "url": RESEARCH_AGENT_URL,
        "avatar": "🔬",
        "system_prompt": (
            "你是一名技术研究助手。请对主题进行简明研究，"
            "用 2-3 句话总结核心概念。回答用中文，控制在 150 字以内。"
            "直接输出最终答案，不要输出思考过程。"
        ),
    },
    "writing": {
        "name": "Writing Agent",
        "url": WRITING_AGENT_URL,
        "avatar": "✍️",
        "system_prompt": (
            "你是一名技术博客作者。请基于提供的摘要，"
            "写一篇结构清晰的 Markdown 入门文章，包含引言、核心概念、应用场景、总结。"
            "回答用中文。直接输出文章，不要输出思考过程。"
        ),
    },
    "review": {
        "name": "Review Agent",
        "url": WRITING_AGENT_URL,
        "avatar": "🧐",
        "system_prompt": (
            "你是一名技术编辑。请审校提供的文章，"
            "列出 3-5 条具体改进建议，包括内容准确性、结构清晰度、可读性等方面。"
            "回答用中文。直接输出建议，不要输出思考过程。"
        ),
    },
    "code": {
        "name": "Code Agent",
        "url": RESEARCH_AGENT_URL,
        "avatar": "💻",
        "system_prompt": (
            "你是一名资深工程师。请根据主题提供一个简洁的代码示例或命令行示例，"
            "帮助读者快速上手。代码要有注释，说明关键步骤。"
            "回答用中文。直接输出代码和说明，不要输出思考过程。"
        ),
    },
    "summary": {
        "name": "Summary Agent",
        "url": WRITING_AGENT_URL,
        "avatar": "📝",
        "system_prompt": (
            "你是一名会议助理。请根据整个会议讨论内容，"
            "用 3-5 条 bullet points 总结核心结论和下一步行动建议。"
            "回答用中文。直接输出总结，不要输出思考过程。"
        ),
    },
}


# ============== 辅助函数 ==============

def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def create_meeting(topic: str, mode: str = "pipeline", max_rounds: int = 1) -> Meeting:
    meeting_id = str(uuid.uuid4())[:8]

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

    mode_text = "流水线模式" if mode == "pipeline" else f"圆桌讨论模式（{max_rounds} 轮）"

    meeting = Meeting(
        id=meeting_id,
        topic=topic,
        mode=mode,
        max_rounds=max_rounds,
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
    return msg


def update_participant_status(meeting_id: str, participant_id: str, status: str):
    meeting = meetings[meeting_id]
    for p in meeting.participants:
        if p.id == participant_id:
            p.status = status


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ============== Agent 调用 ==============

async def call_agent(agent_key: str, input_text: str, max_tokens: int = None) -> str:
    """直接调用 agent 的 LLM，不走 HTTP（减少一次网络跳转）"""
    agent = AGENTS[agent_key]
    default_max_tokens = {"writing": 4000, "summary": 2000, "review": 2000}.get(agent_key, 1500)
    result = call_llm(
        agent["system_prompt"],
        input_text,
        max_tokens=max_tokens or default_max_tokens,
    )
    if result:
        cleaned = result.split("</think>")[-1].strip()
        return cleaned
    return f"{agent['name']} 暂时无法回答。"


async def run_agent_step(meeting_id: str, agent_key: str, input_text: str, context: str = ""):
    """运行单个 agent 步骤，带上完整会议上下文"""
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

    result = await call_agent(agent_key, full_input)

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


async def run_meeting_flow(meeting_id: str, topic: str):
    """运行默认会议流程：research -> writing -> review -> code -> summary
    每个 agent 都能看到之前所有发言的上下文
    """

    # Research Agent
    async for event in run_agent_step(meeting_id, "research", f"请研究这个主题：{topic}"):
        yield event

    # Writing Agent
    context = build_meeting_context(meeting_id)
    writing_input = f"主题：{topic}\n\n请基于会议上下文和主题写一篇文章。"
    async for event in run_agent_step(meeting_id, "writing", writing_input, context):
        yield event

    # Review Agent
    context = build_meeting_context(meeting_id)
    review_input = f"主题：{topic}\n\n请审校 Writing Agent 的文章，给出改进建议。"
    async for event in run_agent_step(meeting_id, "review", review_input, context):
        yield event

    # Code Agent
    context = build_meeting_context(meeting_id)
    code_input = f"主题：{topic}\n\n请提供一个简洁的代码示例或命令行示例。"
    async for event in run_agent_step(meeting_id, "code", code_input, context):
        yield event

    # Summary Agent
    context = build_meeting_context(meeting_id)
    summary_input = f"主题：{topic}\n\n请总结整个会议的核心结论和下一步建议。"
    async for event in run_agent_step(meeting_id, "summary", summary_input, context):
        yield event

    yield sse_event("system", {"meeting_id": meeting_id, "content": "会议流程结束，你可以继续提问。"})


async def run_roundtable_flow(meeting_id: str, topic: str, max_rounds: int = 1):
    """真实圆桌讨论模式
    - Moderator 控制发言顺序
    - 每个 agent 可以决定是否回应（说 PASS 跳过）
    - 优化：agent 自我决策和正式发言合并为一次 LLM 调用
    """
    discussion_agents = ["research", "writing", "review", "code", "summary"]

    # Moderator 开场
    opening = f"欢迎来到圆桌讨论会。今天我们要讨论的主题是：{topic}。请各位专家结合上下文发表观点，如果暂时无话可补充可以说 PASS。"
    async for event in run_agent_step(meeting_id, "moderator", opening):
        yield event

    for round_num in range(1, max_rounds + 1):
        yield sse_event("system", {"meeting_id": meeting_id, "content": f"=== 第 {round_num} 轮讨论 ==="})

        for agent_key in discussion_agents:
            context = build_meeting_context(meeting_id, max_chars_per_msg=1200)

            # 第一轮保底：Research 和 Writing 必须发言，确保讨论有基础内容
            is_first_round = round_num == 1
            force_speak = is_first_round and agent_key in ["research", "writing"]

            # agent 自我判断是否发言：有观点直接说，无话则 PASS（一次 LLM 调用）
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
            # 圆桌模式下限制单次发言长度，降低 LLM 耗时和上下文膨胀
            response = await call_agent(agent_key, agent_prompt, max_tokens=1200)

            if response.strip().upper().startswith("PASS"):
                continue

            # 直接添加 agent 发言消息（不再调用一次 LLM）
            update_participant_status(meeting_id, agent_key, "thinking")
            yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "thinking"})
            await asyncio.sleep(0.3)

            update_participant_status(meeting_id, agent_key, "speaking")
            yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "speaking"})

            msg = add_message(meeting_id, agent_key, response)
            yield sse_event("message", msg.model_dump())

            update_participant_status(meeting_id, agent_key, "idle")
            yield sse_event("status", {"meeting_id": meeting_id, "participant_id": agent_key, "status": "idle"})

    # 保底：如果没有任何 agent 发过言，强制 Research 发言
    has_agent_spoken = any(m.participant_id in discussion_agents for m in meetings[meeting_id].messages)
    if not has_agent_spoken:
        context = build_meeting_context(meeting_id, max_chars_per_msg=1200)
        async for event in run_agent_step(meeting_id, "research", f"请研究这个主题：{topic}", context):
            yield event

    # Moderator 总结
    context = build_meeting_context(meeting_id, max_chars_per_msg=1200)
    closing_prompt = (
        f"你是主持人。会议主题：{topic}。\n\n"
        f"当前讨论上下文：\n{context}\n\n"
        f"请对本次圆桌讨论做简短总结。"
    )
    async for event in run_agent_step(meeting_id, "moderator", closing_prompt):
        yield event

    yield sse_event("system", {"meeting_id": meeting_id, "content": "圆桌会议结束。"})


# ============== API 路由 ==============

@app.get("/")
async def serve_react():
    return FileResponse("/app/web/static/index.html")


@app.get("/api/meetings/{meeting_id}")
async def get_meeting(meeting_id: str):
    if meeting_id not in meetings:
        return {"error": "Meeting not found"}, 404
    return meetings[meeting_id].model_dump()


class CreateMeetingRequest(BaseModel):
    topic: str
    mode: str = "pipeline"  # pipeline | roundtable
    max_rounds: int = 1  # 仅圆桌模式生效，范围 1-10


@app.post("/api/meetings")
async def create_meeting_api(req: CreateMeetingRequest):
    max_rounds = max(1, min(10, req.max_rounds)) if req.mode == "roundtable" else 1
    meeting = create_meeting(req.topic, mode=req.mode, max_rounds=max_rounds)
    return meeting.model_dump()


class SendMessageRequest(BaseModel):
    content: str


@app.post("/api/meetings/{meeting_id}/messages")
async def send_user_message(meeting_id: str, req: SendMessageRequest):
    if meeting_id not in meetings:
        return {"error": "Meeting not found"}, 404

    msg = add_message(meeting_id, "user", req.content)
    return msg.model_dump()


@app.get("/api/meetings/{meeting_id}/events")
async def meeting_events(meeting_id: str):
    """SSE 实时事件流"""
    if meeting_id not in meetings:
        return {"error": "Meeting not found"}, 404

    async def event_stream():
        # 先推送当前会议状态
        meeting = meetings[meeting_id]
        yield sse_event("init", meeting.model_dump())

        # 如果是新会议且只有系统消息，自动运行对应模式流程
        if len(meeting.messages) == 1:
            if meeting.mode == "roundtable":
                async for event in run_roundtable_flow(meeting_id, meeting.topic, max_rounds=meeting.max_rounds):
                    yield event
            else:
                async for event in run_meeting_flow(meeting_id, meeting.topic):
                    yield event

        # 保持连接，后续用户发送消息时也可以推送
        while meeting.status == "active":
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/meetings/{meeting_id}/run")
async def run_agents(meeting_id: str):
    """手动触发 agent 运行（用于用户追加消息后）"""
    if meeting_id not in meetings:
        return {"error": "Meeting not found"}, 404

    meeting = meetings[meeting_id]
    last_user_msg = next(
        (m for m in reversed(meeting.messages) if m.participant_id == "user"),
        None
    )
    topic = last_user_msg.content if last_user_msg else meeting.topic

    async def event_stream():
        if meeting.mode == "roundtable":
            async for event in run_roundtable_flow(meeting_id, topic, max_rounds=meeting.max_rounds):
                yield event
        else:
            async for event in run_meeting_flow(meeting_id, topic):
                yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
