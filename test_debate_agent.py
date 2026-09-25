"""debate_agent 协议与行为测试（TestClient，无真实端口）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient

from debate_agent.main import app, parse_debate_input, build_system_prompt


def _msg(text):
    return {
        "messageId": "m1",
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }


def _send(client, text):
    resp = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {"message": _msg(text)},
        },
    )
    assert resp.status_code == 200, resp.text
    rpc_resp = resp.json()
    assert rpc_resp.get("error") is None, rpc_resp
    return rpc_resp["result"]


INPUT = (
    "[辩题/MOTION] AI 会取代大多数工作吗\n"
    "[角色/PERSONA] 苏格拉底（追问式，承认无知）\n"
    "[立场/STANCE] 正方\n"
    "[对手论点/OPPONENT_ARGUMENTS]\n1. 自动化历史创造新岗位 [来源](https://a.com)\n"
)


def test_parse_debate_input_sections():
    parsed = parse_debate_input(INPUT)
    assert "AI" in parsed["motion"]
    assert "苏格拉底" in parsed["persona"]
    assert parsed["stance"] == "正方"
    assert "https://a.com" in parsed["opponent"]
    assert parse_debate_input("no sections")["motion"] == ""


def test_system_prompt_contains_grounding_rules():
    prompt = build_system_prompt()
    assert "来源" in prompt
    assert "不得编造" in prompt or "绝不编造" in prompt


def test_missing_motion_fails_fast(monkeypatch):
    import debate_agent.main as m

    monkeypatch.setattr(m, "call_llm", lambda *a, **k: None)
    client = TestClient(app)
    task = _send(client, "[角色/PERSONA] x\n[立场/STANCE] 正方")
    assert task["status"]["state"] == "TASK_STATE_FAILED"
    assert "辩题" in task["status"]["message"]["parts"][0]["text"]


def test_no_sources_no_llm_no_fabricated_links(monkeypatch):
    import debate_agent.main as m

    monkeypatch.setattr(m, "web_search", lambda q, max_results=5: [])
    monkeypatch.setattr(m, "call_llm", lambda *a, **k: None)
    client = TestClient(app)
    task = _send(client, INPUT)
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    text = task["artifacts"][0]["parts"][0]["text"]
    assert "](http" not in text, "must not fabricate citation links"
    assert "LLM 服务不可用" in text


def test_sources_flow_into_argument(monkeypatch):
    import debate_agent.main as m

    captured = {}

    def fake_llm(system, user, **kw):
        captured["system"] = system
        captured["user"] = user
        return "论点... [来源1](https://real.com)"

    monkeypatch.setattr(
        m, "web_search",
        lambda q, max_results=5: [{"title": "t", "url": "https://real.com", "snippet": "s"}],
    )
    monkeypatch.setattr(m, "call_llm", fake_llm)
    monkeypatch.setattr(
        m, "call_llm_stream",
        lambda system, user, **kw: iter(["chunk"]),
    )
    client = TestClient(app)
    task = _send(client, INPUT)
    text = task["artifacts"][0]["parts"][0]["text"]
    assert "https://real.com" in text
    assert "https://real.com" in captured["user"], "sources must be in the LLM prompt"


def test_agent_card_declares_debate_skill():
    client = TestClient(app)
    card = client.get("/.well-known/agent-card.json").json()
    assert card["name"] == "debate-agent"
    assert card["skills"][0]["id"] == "debate"
