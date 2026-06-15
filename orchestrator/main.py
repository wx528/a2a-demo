"""
Orchestrator - A2A 编排器示例
流程：
1. 接收用户主题
2. 调用 research-agent 获取研究摘要
3. 调用 writing-agent 基于摘要生成文章
4. 返回最终结果
"""

import os
import uuid
import httpx
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import TextPart, Message, TaskSendParams


ORCHESTRATOR_PORT = int(os.getenv("PORT", 8000))
RESEARCH_AGENT_URL = os.getenv("RESEARCH_AGENT_URL", "http://research-agent:8001")
WRITING_AGENT_URL = os.getenv("WRITING_AGENT_URL", "http://writing-agent:8002")


app = FastAPI(title="A2A Orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateArticleRequest(BaseModel):
    topic: str


async def fetch_agent_card(agent_url: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{agent_url}/.well-known/agent.json")
        resp.raise_for_status()
        return resp.json()


async def send_task(agent_url: str, text: str) -> dict:
    params = TaskSendParams(
        message=Message(
            role="user",
            parts=[TextPart(text=text)],
        )
    )
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{agent_url}/tasks/send",
            json=params.model_dump(),
        )
        resp.raise_for_status()
        return resp.json()


def extract_agent_text(task: dict) -> str:
    """从任务结果中提取 agent 返回的文本"""
    for msg in task.get("messages", []):
        if msg.get("role") == "agent":
            for part in msg.get("parts", []):
                if part.get("type") == "text":
                    return part.get("text", "")
    return ""


@app.get("/")
async def root():
    return {
        "service": "A2A Orchestrator",
        "agents": {
            "research": RESEARCH_AGENT_URL,
            "writing": WRITING_AGENT_URL,
        },
    }


@app.get("/agents")
async def list_agents():
    """列出所有已注册的 agent 及其能力"""
    results = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, url in [("research", RESEARCH_AGENT_URL), ("writing", WRITING_AGENT_URL)]:
            try:
                resp = await client.get(f"{url}/.well-known/agent.json")
                results[name] = resp.json()
            except Exception as e:
                results[name] = {"error": str(e), "url": url}
    return results


@app.post("/create-article")
async def create_article(req: CreateArticleRequest):
    """
    完整工作流：研究 -> 写作
    """
    topic = req.topic

    # Step 1: 调用 research agent
    try:
        research_task = await send_task(RESEARCH_AGENT_URL, topic)
        research_summary = extract_agent_text(research_task)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Research agent failed: {e}")

    if not research_summary:
        raise HTTPException(status_code=502, detail="Research agent returned empty result")

    # Step 2: 调用 writing agent
    try:
        writing_task = await send_task(WRITING_AGENT_URL, research_summary)
        article = extract_agent_text(writing_task)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Writing agent failed: {e}")

    return {
        "topic": topic,
        "research_summary": research_summary,
        "article": article,
        "workflow": ["research-agent", "writing-agent"],
    }


@app.post("/direct/{agent_name}")
async def direct_call(agent_name: str, req: CreateArticleRequest):
    """直接调用某个 agent，方便单独测试"""
    url_map = {
        "research": RESEARCH_AGENT_URL,
        "writing": WRITING_AGENT_URL,
    }
    if agent_name not in url_map:
        raise HTTPException(status_code=404, detail="Unknown agent")

    task = await send_task(url_map[agent_name], req.topic)
    return {
        "agent": agent_name,
        "result": extract_agent_text(task),
        "raw_task": task,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=ORCHESTRATOR_PORT)
