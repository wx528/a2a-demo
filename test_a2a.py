"""A2A JSON-RPC core flow integration test (using TestClient, no real ports needed)"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from research_agent.main import app as research_app
from writing_agent.main import app as writing_app
from orchestrator.main import app as orch_app, A2AJSONRPCClient


def test_agent_card():
    for name, app in [("research", research_app), ("writing", writing_app)]:
        client = TestClient(app)
        resp = client.get("/.well-known/agent.json")
        assert resp.status_code == 200, f"{name} agent card failed"
        card = resp.json()
        assert "supportedInterfaces" in card, f"{name} missing supportedInterfaces"
        assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
        assert "capabilities" in card
        print(f"[OK] {name} agent card: {card['name']}")


def test_tasks_send():
    client = TestClient(research_app)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tasks/send",
        "params": {
            "message": {
                "messageId": "msg-001",
                "role": "user",
                "parts": [{"text": "kubernetes"}],
            }
        },
    }
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 200, resp.text
    rpc_resp = resp.json()
    assert rpc_resp.get("error") is None, rpc_resp
    task = rpc_resp["result"]
    assert task["status"]["state"] == "completed"
    assert task["artifacts"], "result should be in artifacts"
    text = task["artifacts"][0]["parts"][0]["text"]
    assert "kubernetes" in text.lower() or "Kubernetes" in text
    print(f"[OK] tasks/send: taskId={task['id']}, text_len={len(text)}")
    return task["id"]


def test_tasks_get(task_id: str):
    client = TestClient(research_app)
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tasks/get",
        "params": {"id": task_id},
    }
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 200
    rpc_resp = resp.json()
    assert rpc_resp["result"]["id"] == task_id
    print("[OK] tasks/get")


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
    test_agent_card()
    task_id = test_tasks_send()
    test_tasks_get(task_id)
    test_orchestrator()
    print("\nAll A2A core tests passed!")
