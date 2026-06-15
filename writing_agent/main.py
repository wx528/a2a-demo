"""
Writing Agent - A2A 示例 Agent
能力：基于研究摘要，生成一篇格式化文章
"""

import os
import uuid
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import (
    TaskStatus, TextPart, Message, Task, TaskSendParams,
    AgentCard, AgentSkill, AgentCapabilities
)
from shared.llm_client import call_llm


AGENT_PORT = int(os.getenv("PORT", 8002))
AGENT_HOST = os.getenv("HOST", "localhost")
AGENT_URL = f"http://{AGENT_HOST}:{AGENT_PORT}"


def generate_article(research_summary: str) -> str:
    """优先调用 LLM 生成文章，失败则回退到模板"""
    lines = research_summary.split("\n")
    topic = "该主题"
    for line in lines:
        if line.startswith("主题："):
            topic = line.replace("主题：", "").strip()
            break

    system_prompt = (
        "你是一名技术博客作者。请根据提供的研究摘要，"
        "写一篇结构清晰的 Markdown 格式入门文章。"
        "文章包含：引言、核心概念、应用场景、总结四个部分。"
        "回答用中文。"
        "直接输出文章正文，不要输出思考过程。"
    )

    llm_result = call_llm(
        system_prompt,
        f"请基于以下摘要写一篇文章：\n\n{research_summary}",
        max_tokens=4000,
    )
    if llm_result:
        # 清理可能的思考标签
        cleaned = llm_result.split("</think>")[-1].strip()
        return cleaned

    # LLM 不可用时回退
    article = f"""# {topic} 入门指南

## 引言

{topic} 是当前技术领域的重要话题。本文将从基础概念出发，帮助读者快速理解其核心思想。

## 核心概念

{research_summary}

## 应用场景

- 企业级系统构建
- 自动化流程编排
- 提升开发运维效率

## 总结

掌握 {topic} 对于现代软件工程师来说越来越重要，建议从官方文档和实践项目入手。

（本地回退，未调用 LLM）
"""
    return article


agent_card = AgentCard(
    name="writing-agent",
    description="写作型 Agent，基于研究摘要生成格式化文章",
    url=AGENT_URL,
    version="1.0.0",
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
    skills=[
        AgentSkill(
            id="write-article",
            name="文章写作",
            description="根据已有素材生成 Markdown 格式文章",
            tags=["writing", "markdown"],
            examples=["根据 Kubernetes 摘要写文章"],
        )
    ],
)


tasks: dict[str, Task] = {}


app = FastAPI(title="Writing Agent (A2A)")
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
    task_id = params.id or str(uuid.uuid4())
    session_id = params.sessionId or str(uuid.uuid4())

    user_text = ""
    for part in params.message.parts:
        if part.type == "text":
            user_text += part.text

    task = Task(
        id=task_id,
        sessionId=session_id,
        status=TaskStatus.WORKING,
        messages=[params.message],
        history=[params.message],
    )
    tasks[task_id] = task

    await asyncio.sleep(0.5)

    article = generate_article(user_text)

    agent_message = Message(
        role="agent",
        parts=[TextPart(text=article)],
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


@app.get("/")
async def root():
    return {"agent": "writing-agent", "protocol": "A2A", "url": AGENT_URL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
