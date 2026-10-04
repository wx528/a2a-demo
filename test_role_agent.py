"""role_agent 服务测试：Agent 卡片、SendMessage fallback、流式端点（无 LLM key 场景）"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from fastapi.testclient import TestClient

CARD_PATH = "/.well-known/agent-card.json"


def _msg(mid: str, text: str) -> dict:
    return {"messageId": mid, "role": "ROLE_USER", "parts": [{"text": text}]}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("ROLE", "linus")
    import role_agent.main as m

    m = importlib.reload(m)
    return TestClient(m.app)


def test_agent_card(client):
    resp = client.get(CARD_PATH)
    assert resp.status_code == 200
    card = resp.json()
    assert "Linus" in card["name"]
    assert card["description"], "card description (role duty) must be non-empty"
    assert card["capabilities"]["streaming"] is True
    assert card["skills"], "role card must declare its stage duties as skills"


def test_send_message_fallback(client):
    resp = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {"message": _msg("m-1", "评估风险")},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("error") is None, body
    task = body["result"]
    assert task is not None
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task["status"]
    text = task["artifacts"][0]["parts"][0]["text"]
    assert "挑战者" in text and "暂未能生成发言" in text, text


def test_stream_endpoint(client):
    resp = client.post(
        "/rpc/stream",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendStreamingMessage",
            "params": {"message": _msg("m-2", "评估风险")},
        },
    )
    assert resp.status_code == 200, resp.text
    assert "data:" in resp.text


def test_unknown_role_fails_fast(monkeypatch):
    monkeypatch.setenv("ROLE", "bogus")
    sys.modules.pop("role_agent.main", None)
    with pytest.raises(ValueError):
        importlib.import_module("role_agent.main")


def test_role_personas_cover_all_roles():
    import role_agent.main as m

    assert set(m.ROLE_PERSONA_PROMPTS) == {"ada", "turing", "linus", "sage"}
    for prompt in m.ROLE_PERSONA_PROMPTS.values():
        assert "简体中文" in prompt
        assert "观点标题" in prompt
        assert "不得虚构" in prompt
    assert "# UNVERIFIED" in m.ROLE_PERSONA_PROMPTS["ada"]
