"""
Research Agent - A2A 示例 Agent
能力：接收一个主题，返回该主题的研究摘要
"""

import os
import uuid
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import (
    TaskStatus, TextPart, Message, Task, TaskSendParams,
    AgentCard, AgentSkill, AgentCapabilities
)
from shared.llm_client import call_llm


AGENT_PORT = int(os.getenv("PORT", 8001))
AGENT_HOST = os.getenv("HOST", "localhost")
AGENT_URL = f"http://{AGENT_HOST}:{AGENT_PORT}"


# 模拟知识库
KNOWLEDGE_BASE = {
    "kubernetes": "Kubernetes 是一个开源的容器编排平台，由 Google 设计并捐赠给 CNCF。",
    "a2a": "A2A (Agent-to-Agent) 是 Google 提出的开放协议，用于不同 AI Agent 之间的互操作。",
    "docker": "Docker 是一个开源的容器化平台，可以让应用及其依赖打包成标准化单元。",
    "python": "Python 是一种解释型、高级、通用的编程语言，广泛应用于 AI 和 Web 开发。",
}


def generate_summary(topic: str) -> str:
    """优先调用 LLM 生成摘要，失败则回退到本地知识库"""
    system_prompt = (
        "你是一名技术研究助手。用户会给你一个技术主题，"
        "请用 2-3 句话简明扼要地总结这个主题的核心概念和用途。"
        "回答用中文，控制在 150 字以内。"
        "直接输出最终答案，不要输出思考过程。"
    )

    llm_result = call_llm(system_prompt, f"请研究这个主题：{topic}")
    if llm_result:
        # 如果模型输出了 <think> 等思考标签，只取最终答案
        cleaned = llm_result.split("</think>")[-1].strip()
        return f"【研究摘要】\n主题：{topic}\n\n{cleaned}"

    # LLM 不可用时回退
    topic_lower = topic.lower()
    base = KNOWLEDGE_BASE.get(topic_lower, f"关于 {topic} 的信息有限，建议进一步搜索。")
    return f"【研究摘要】\n主题：{topic}\n\n{base}\n\n（本地回退，未调用 LLM）"


agent_card = AgentCard(
    name="research-agent",
    description="研究型 Agent，接收主题并返回研究摘要",
    url=AGENT_URL,
    version="1.0.0",
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    capabilities=AgentCapabilities(streaming=True, pushNotifications=False),
    skills=[
        AgentSkill(
            id="research",
            name="主题研究",
            description="对给定主题进行快速研究并生成摘要",
            tags=["research", "summary"],
            examples=["研究 Kubernetes", "研究 A2A 协议"],
        )
    ],
)


# 内存任务存储
tasks: dict[str, Task] = {}


app = FastAPI(title="Research Agent (A2A)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/.well-known/agent.json")
async def get_agent_card():
    return agent_card.model_dump()


@app.post("/tasks/send")
async def send_task(params: TaskSendParams):
    """同步发送任务，返回最终结果"""
    task_id = params.id or str(uuid.uuid4())
    session_id = params.sessionId or str(uuid.uuid4())

    # 提取用户输入
    user_text = ""
    for part in params.message.parts:
        if part.type == "text":
            user_text += part.text

    # 创建任务
    task = Task(
        id=task_id,
        sessionId=session_id,
        status=TaskStatus.WORKING,
        messages=[params.message],
        history=[params.message],
    )
    tasks[task_id] = task

    # 模拟处理耗时
    await asyncio.sleep(0.5)

    # 生成研究结果
    summary = generate_summary(user_text)

    agent_message = Message(
        role="agent",
        parts=[TextPart(text=summary)],
    )

    task.status = TaskStatus.COMPLETED
    task.messages.append(agent_message)
    task.history.append(agent_message)

    return task.model_dump()


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id].model_dump()


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    tasks[task_id].status = TaskStatus.CANCELED
    return tasks[task_id].model_dump()


@app.get("/")
async def root():
    return {"agent": "research-agent", "protocol": "A2A", "url": AGENT_URL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
