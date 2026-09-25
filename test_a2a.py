"""A2A v1.0 (JSON-RPC 绑定) 核心流程测试（TestClient / ASGITransport，无需真实端口）"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from research_agent.main import app as research_app
from writing_agent.main import app as writing_app
from orchestrator.main import A2AJSONRPCClient

CARD_PATH = "/.well-known/agent-card.json"
LEGACY_CARD_PATH = "/.well-known/agent.json"


def rpc(client, method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _send_research_message(message_id: str, text: str) -> dict:
    client = TestClient(research_app)
    rpc_resp = rpc(
        client,
        "SendMessage",
        {
            "message": {
                "messageId": message_id,
                "role": "ROLE_USER",
                "parts": [{"text": text}],
            }
        },
    )
    assert rpc_resp.get("error") is None, rpc_resp
    return rpc_resp["result"]


def test_agent_card_canonical_path():
    for name, app in [("research", research_app), ("writing", writing_app)]:
        client = TestClient(app)
        resp = client.get(CARD_PATH)
        assert resp.status_code == 200, f"{name} agent card failed"
        card = resp.json()
        assert "supportedInterfaces" in card, f"{name} missing supportedInterfaces"
        assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
        assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
        assert "capabilities" in card
        print(f"[OK] {name} agent card: {card['name']}")


def test_agent_card_legacy_path_still_served():
    client = TestClient(research_app)
    resp = client.get(LEGACY_CARD_PATH)
    assert resp.status_code == 200
    assert "supportedInterfaces" in resp.json()
    print("[OK] legacy agent.json path still served")


def test_send_message_v1():
    task = _send_research_message("msg-001", "kubernetes")
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task["status"]
    assert task["artifacts"], "result should be in artifacts"
    text = task["artifacts"][0]["parts"][0]["text"]
    assert text, "artifact text should be non-empty"
    print(f"[OK] SendMessage: taskId={task['id']}, text_len={len(text)}")


def test_timestamp_millisecond_precision():
    task = _send_research_message("msg-ts", "timestamp check")
    ts = task["status"]["timestamp"]
    # 规范模式: YYYY-MM-DDTHH:mm:ss.sssZ
    assert ts.endswith("Z"), ts
    frac = ts.split(".")[-1][:-1]  # 去掉末尾 Z
    assert len(frac) == 3, f"expected millisecond precision, got: {ts}"
    print(f"[OK] timestamp format: {ts}")


def test_get_task_v1():
    task_id = _send_research_message("msg-get", "get task check")["id"]
    client = TestClient(research_app)
    rpc_resp = rpc(client, "GetTask", {"id": task_id})
    assert rpc_resp.get("error") is None, rpc_resp
    assert rpc_resp["result"]["id"] == task_id
    print("[OK] GetTask")


def test_legacy_method_alias():
    client = TestClient(research_app)
    payload = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tasks/send",
        "params": {
            "message": {
                "messageId": "msg-legacy",
                "role": "user",
                "parts": [{"text": "docker"}],
            }
        },
    }
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 200, resp.text
    rpc_resp = resp.json()
    assert rpc_resp.get("error") is None, rpc_resp
    assert rpc_resp["result"]["status"]["state"] == "TASK_STATE_COMPLETED"
    print("[OK] legacy tasks/send alias (with v0.x enum tolerance)")


def test_error_format_google_rpc_status():
    client = TestClient(research_app)
    rpc_resp = rpc(client, "GetTask", {"id": "nonexistent-task-id"})
    err = rpc_resp.get("error")
    assert err, "expected JSON-RPC error for unknown task"
    assert err["code"] == -32001, err
    data = err["data"]
    assert isinstance(data, list), f"data must be an array of ProtoJSON Any, got: {data}"
    info = data[0]
    assert info["@type"] == "type.googleapis.com/google.rpc.ErrorInfo"
    assert info["reason"] == "TASK_NOT_FOUND"
    assert info["domain"] == "a2a-protocol.org"
    print("[OK] google.rpc.ErrorInfo error format")


def test_send_message_does_not_block_event_loop():
    """慢任务执行期间，同一事件循环上的其他请求必须不被阻塞。"""
    import httpx
    from shared.a2a_server import A2AJSONRPCServer
    from shared.models import (
        AgentCapabilities,
        AgentCard,
        AgentInterface,
        Task,
        TaskState,
    )

    def slow_process(task: Task, store):
        store.update_status(task, TaskState.WORKING, "slow...")
        time.sleep(1.0)
        store.add_artifact(task, "response", "done")
        store.update_status(task, TaskState.COMPLETED, "done")

    card = AgentCard(
        name="slow-agent",
        description="test",
        supported_interfaces=[
            AgentInterface(url="http://test/rpc", protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    )
    app = A2AJSONRPCServer(agent_card=card, process_task=slow_process).build_app()

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:

            async def slow_request():
                r = await ac.post(
                    "/rpc",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "SendMessage",
                        "params": {
                            "message": {
                                "messageId": "m1",
                                "role": "ROLE_USER",
                                "parts": [{"text": "slow"}],
                            }
                        },
                    },
                )
                return r.json()

            slow_task = asyncio.create_task(slow_request())
            await asyncio.sleep(0.1)  # 让慢请求先进入处理
            t0 = time.monotonic()
            fast_resp = await ac.get("/")
            fast_elapsed = time.monotonic() - t0
            slow_result = await slow_task
            return fast_elapsed, fast_resp.status_code, slow_result

    fast_elapsed, fast_code, slow_result = asyncio.run(scenario())
    assert fast_code == 200
    assert fast_elapsed < 0.5, f"event loop was blocked: GET / took {fast_elapsed:.2f}s"
    assert slow_result["result"]["status"]["state"] == "TASK_STATE_COMPLETED"
    print(f"[OK] non-blocking: GET / during slow task took {fast_elapsed:.3f}s")


def test_orchestrator():
    client = A2AJSONRPCClient("http://localhost:8001")
    assert client.agent_url == "http://localhost:8001"
    assert client.rpc_url == "http://localhost:8001/rpc"
    print("[OK] A2AJSONRPCClient")


def test_model_serialization():
    from shared.models import AgentCard, AgentInterface

    card = AgentCard(
        name="test",
        description="test",
        supported_interfaces=[AgentInterface(url="http://x/rpc", protocol_binding="JSONRPC", protocol_version="1.0")],
        version="1.0.0",
        capabilities={"streaming": True},
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    )
    d = card.model_dump(by_alias=True, exclude_none=True)
    assert "supportedInterfaces" in d
    assert "protocolBinding" in d["supportedInterfaces"][0]
    print("[OK] model serialization")


if __name__ == "__main__":
    test_model_serialization()
    test_agent_card_canonical_path()
    test_agent_card_legacy_path_still_served()
    test_send_message_v1()
    test_timestamp_millisecond_precision()
    test_get_task_v1()
    test_legacy_method_alias()
    test_error_format_google_rpc_status()
    test_send_message_does_not_block_event_loop()
    test_orchestrator()
    print("\nAll A2A core tests passed!")
