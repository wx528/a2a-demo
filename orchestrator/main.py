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
import uuid
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import JSONRPCRequest, JSONRPCResponse, Message, Part, Role


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


class A2AJSONRPCClient:
    """极简 A2A JSON-RPC 2.0 客户端。"""

    def __init__(self, agent_url: str):
        self.agent_url = agent_url.rstrip("/")
        self.rpc_url = f"{self.agent_url}/rpc"

    async def call(self, method: str, params: Dict[str, Any]) -> Any:
        payload = JSONRPCRequest(
            id=str(uuid.uuid4()),
            method=method,
            params=params,
        ).model_dump()

        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            resp = await client.post(
                self.rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            rpc_resp = JSONRPCResponse.model_validate(resp.json())

        if rpc_resp.error:
            raise RuntimeError(
                f"A2A RPC error [{rpc_resp.error.code}]: {rpc_resp.error.message}"
            )
        return rpc_resp.result

    async def send_message(self, text: str) -> Dict[str, Any]:
        params = {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"text": text}],
            }
        }
        return await self.call("tasks/send", params)

    async def fetch_agent_card(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            resp = await client.get(f"{self.agent_url}/.well-known/agent.json")
            resp.raise_for_status()
            return resp.json()


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
    async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
        for name, url in [("research", RESEARCH_AGENT_URL), ("writing", WRITING_AGENT_URL)]:
            try:
                resp = await client.get(f"{url}/.well-known/agent.json")
                results[name] = resp.json()
            except Exception as e:
                results[name] = {"error": str(e), "url": url}
    return results


@app.post("/create-article")
async def create_article(req: CreateArticleRequest):
    """完整工作流：研究 -> 写作"""
    topic = req.topic

    # Step 1: 调用 research agent
    try:
        research_client = A2AJSONRPCClient(RESEARCH_AGENT_URL)
        research_task = await research_client.send_message(topic)
        research_summary = extract_agent_text(research_task)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Research agent failed: {e}")

    if not research_summary:
        raise HTTPException(status_code=502, detail="Research agent returned empty result")

    # Step 2: 调用 writing agent
    try:
        writing_client = A2AJSONRPCClient(WRITING_AGENT_URL)
        writing_task = await writing_client.send_message(research_summary)
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
