"""
Orchestrator - A2A 编排器示例（JSON-RPC 2.0 客户端）
流程：
1. 启动时通过 Agent Card 动态发现 agent（AGENT_URLS 或旧版环境变量）
2. 接收用户主题
3. 通过 JSON-RPC 调用 research-agent 获取研究摘要
4. 通过 JSON-RPC 调用 writing-agent 基于摘要生成文章
5. 返回最终结果
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env
load_env()
from shared.a2a_client import A2AJSONRPCClient
from orchestrator.registry import AgentRegistry


ORCHESTRATOR_PORT = int(os.getenv("PORT", 8000))

logger = logging.getLogger("orchestrator")


def _agent_urls() -> List[str]:
    """优先 AGENT_URLS（逗号分隔，动态发现）；否则回退旧版成对变量。"""
    urls = [u.strip() for u in os.getenv("AGENT_URLS", "").split(",") if u.strip()]
    if urls:
        return urls
    legacy = []
    for var, default in [
        ("RESEARCH_AGENT_URL", "http://research-agent:8001"),
        ("WRITING_AGENT_URL", "http://writing-agent:8002"),
    ]:
        url = os.getenv(var, default)
        if url not in legacy:
            legacy.append(url)
    return legacy


AGENT_URLS = _agent_urls()
registry = AgentRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await registry.discover(AGENT_URLS)
    logger.info("discovered agents: %s", registry.names())
    yield


app = FastAPI(title="A2A Orchestrator", lifespan=lifespan)
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


def _resolve_agent(name: str) -> str:
    """先走注册表解析，失败再回退旧版固定地址（保证向后兼容）。"""
    url = registry.resolve(name)
    if url:
        return url
    legacy_map = dict(
        zip(
            ["research", "writing"],
            [os.getenv("RESEARCH_AGENT_URL", "http://research-agent:8001"),
             os.getenv("WRITING_AGENT_URL", "http://writing-agent:8002")],
        )
    )
    if name in legacy_map:
        return legacy_map[name]
    raise HTTPException(status_code=404, detail=f"Unknown agent: {name}")


@app.get("/")
async def root():
    return {
        "service": "A2A Orchestrator",
        "binding": "JSON-RPC 2.0",
        "agents": registry.names() or AGENT_URLS,
    }


@app.get("/agents")
async def list_agents():
    """列出所有已发现 agent 及其 Agent Card。"""
    cards = registry.list()
    if not cards:
        # 发现失败时回退为探测旧版固定地址
        results = {}
        for url in AGENT_URLS:
            try:
                client = A2AJSONRPCClient(url)
                card = await client.fetch_agent_card()
                results[card.get("name", url)] = card
            except Exception as e:
                results[url] = {"error": str(e), "url": url}
        return results
    return {card["name"]: card for card in cards}


@app.post("/agents/refresh")
async def refresh_agents():
    """重新执行发现（新增 agent 后调用，无需重启编排器）。"""
    await registry.discover(AGENT_URLS)
    return {"discovered": registry.names()}


@app.post("/create-article")
async def create_article(req: CreateArticleRequest):
    """完整工作流：研究 -> 写作（按 skill 动态路由）。"""
    topic = req.topic

    research_url = registry.find_by_skill("research") or _resolve_agent("research")
    writing_url = registry.find_by_skill("writing") or _resolve_agent("writing")

    # Step 1: 调用 research agent 获取研究摘要
    research_prompt = (
        "你是一名技术研究助手。请用 2-3 句话简明扼要地总结下面这个技术主题的核心概念和用途。"
        "回答用中文，控制在 150 字以内。直接输出最终答案，不要输出思考过程。\n\n"
        f"主题：{topic}"
    )
    try:
        research_client = A2AJSONRPCClient(research_url)
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
        writing_client = A2AJSONRPCClient(writing_url)
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
    """直接调用某个 agent（支持 card 名称 / 短名 / skill id），方便单独测试。"""
    url = _resolve_agent(agent_name)
    client = A2AJSONRPCClient(url)
    task = await client.send_message(req.topic)
    return {
        "agent": agent_name,
        "result": extract_agent_text(task),
        "raw_task": task,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=ORCHESTRATOR_PORT)
