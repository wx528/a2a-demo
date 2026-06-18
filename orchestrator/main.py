"""
Orchestrator - A2A 编排器示例（JSON-RPC 2.0 客户端）
流程：
1. 接收用户主题
2. 通过 JSON-RPC 调用 research-agent 获取研究摘要
3. 通过 JSON-RPC 调用 writing-agent 基于摘要生成文章
4. 返回最终结果
"""

import os
import sys
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.a2a_client import A2AJSONRPCClient


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


def extract_agent_text(task: Dict[str, Any]) -> str:
    """从 A2A Task 结果中提取第一个 artifact 的文本内容。"""
    artifacts = task.get("artifacts") or []
    if not artifacts:
        return ""
    first = artifacts[0]
    for part in first.get("parts", []):
        if part.get("text"):
            return part["text"]
    return ""


@app.get("/")
async def root():
    return {
        "service": "A2A Orchestrator",
        "binding": "JSON-RPC 2.0",
        "agents": {
            "research": RESEARCH_AGENT_URL,
            "writing": WRITING_AGENT_URL,
        },
    }


@app.get("/agents")
async def list_agents():
    """列出所有已注册 agent 及其 Agent Card。"""
    results = {}
    for name, url in [("research", RESEARCH_AGENT_URL), ("writing", WRITING_AGENT_URL)]:
        try:
            client = A2AJSONRPCClient(url)
            results[name] = await client.fetch_agent_card()
        except Exception as e:
            results[name] = {"error": str(e), "url": url}
    return results


@app.post("/create-article")
async def create_article(req: CreateArticleRequest):
    """完整工作流：研究 -> 写作"""
    topic = req.topic

    # Step 1: 调用 research agent 获取研究摘要
    research_prompt = (
        "你是一名技术研究助手。请用 2-3 句话简明扼要地总结下面这个技术主题的核心概念和用途。"
        "回答用中文，控制在 150 字以内。直接输出最终答案，不要输出思考过程。\n\n"
        f"主题：{topic}"
    )
    try:
        research_client = A2AJSONRPCClient(RESEARCH_AGENT_URL)
        research_task = await research_client.send_message(research_prompt)
        research_summary = extract_agent_text(research_task)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Research agent failed: {e}")

    if not research_summary:
        raise HTTPException(status_code=502, detail="Research agent returned empty result")

    # Step 2: 调用 writing agent 基于摘要生成文章
    writing_prompt = (
        "你是一名技术博客作者。请根据下面提供的研究摘要，"
        "写一篇结构清晰的 Markdown 格式入门文章。"
        "文章包含：引言、核心概念、应用场景、总结四个部分。"
        "回答用中文。直接输出文章正文，不要输出思考过程。\n\n"
        f"研究摘要：\n{research_summary}"
    )
    try:
        writing_client = A2AJSONRPCClient(WRITING_AGENT_URL)
        writing_task = await writing_client.send_message(writing_prompt)
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
    """直接调用某个 agent，方便单独测试。"""
    url_map = {
        "research": RESEARCH_AGENT_URL,
        "writing": WRITING_AGENT_URL,
    }
    if agent_name not in url_map:
        raise HTTPException(status_code=404, detail="Unknown agent")

    client = A2AJSONRPCClient(url_map[agent_name])
    task = await client.send_message(req.topic)
    return {
        "agent": agent_name,
        "result": extract_agent_text(task),
        "raw_task": task,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=ORCHESTRATOR_PORT)
