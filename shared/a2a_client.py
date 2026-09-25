"""
A2A JSON-RPC 2.0 客户端公共组件。
供 orchestrator、web 等模块调用远端 A2A Agent。
"""

import json
import uuid
from typing import Any, Dict, List

import httpx

from .models import JSONRPCRequest, JSONRPCResponse


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

    async def call_raw(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """与 call() 相同，但不抛 JSON-RPC 错误——返回完整响应 dict（含 error 字段）。"""
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
            return resp.json()

    async def stream_send(self, text: str) -> List[Any]:
        """SendStreamingMessage（SSE），返回按序解析的 data 事件 dict 列表。"""
        payload = JSONRPCRequest(
            id=str(uuid.uuid4()),
            method="SendStreamingMessage",
            params={
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"text": text}],
                }
            },
        ).model_dump()
        events: List[Any] = []
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{self.agent_url}/rpc/stream",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[len("data: "):]))
        return events

    async def send_message(self, text: str) -> Dict[str, Any]:
        params = {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "ROLE_USER",
                "parts": [{"text": text}],
            }
        }
        return await self.call("SendMessage", params)

    async def fetch_agent_card(self) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            # v1.0 规范路径为 agent-card.json，旧版 agent.json 作为回退
            resp = await client.get(f"{self.agent_url}/.well-known/agent-card.json")
            if resp.status_code == 404:
                resp = await client.get(f"{self.agent_url}/.well-known/agent.json")
            resp.raise_for_status()
            return resp.json()
