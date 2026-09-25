"""debate_agent 协议与行为测试（TestClient，无真实端口）。"""

import json
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


def _get_task(client, task_id):
    rpc_resp = _rpc(client, "GetTask", {"id": task_id})
    assert rpc_resp.get("error") is None, rpc_resp
    return rpc_resp["result"]


def _rpc(client, method, params):
    resp = client.post(
        "/rpc",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _stream_events(client, text):
    resp = client.post(
        "/rpc/stream",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendStreamingMessage",
            "params": {"message": _msg(text)},
        },
    )
    assert resp.status_code == 200, resp.text
    return [
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]


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


def test_streaming_success_assembles_chunks(monkeypatch):
    import debate_agent.main as m

    monkeypatch.setattr(
        m, "web_search",
        lambda q, max_results=5: [{"title": "t", "url": "https://real.com", "snippet": "s"}],
    )
    monkeypatch.setattr(m, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(
        m, "call_llm_stream",
        lambda system, user, **kw: iter(["Hello ", "debate"]),
    )
    client = TestClient(app)
    events = _stream_events(client, INPUT)

    chunks = [e["artifactUpdate"] for e in events if "artifactUpdate" in e]
    assembled = "".join(c["artifact"]["parts"][0]["text"] for c in chunks)
    assert assembled == "Hello debate", assembled
    assert chunks[-1]["lastChunk"] is True, "final chunk must set lastChunk"

    states = [e["statusUpdate"]["status"]["state"] for e in events if "statusUpdate" in e]
    assert "TASK_STATE_COMPLETED" in states, states

    task_id = [e["task"]["id"] for e in events if "task" in e][0]
    got = _get_task(client, task_id)
    assert got["status"]["state"] == "TASK_STATE_COMPLETED"
    assert got["artifacts"][0]["parts"][0]["text"] == "Hello debate"


def test_streaming_midstream_failure_marks_failed(monkeypatch):
    import debate_agent.main as m

    def bad_stream(system, user, **kw):
        def gen():
            yield "chunk-one"
            raise RuntimeError("stream boom")

        return gen()

    monkeypatch.setattr(m, "web_search", lambda q, max_results=5: [])
    monkeypatch.setattr(m, "call_llm", lambda *a, **k: None)
    monkeypatch.setattr(m, "call_llm_stream", bad_stream)
    client = TestClient(app)
    events = _stream_events(client, INPUT)

    states = [e["statusUpdate"]["status"]["state"] for e in events if "statusUpdate" in e]
    assert "TASK_STATE_FAILED" in states, states

    task_id = [e["task"]["id"] for e in events if "task" in e][0]
    got = _get_task(client, task_id)
    assert got["status"]["state"] == "TASK_STATE_FAILED"
    assert "stream boom" in got["status"]["message"]["parts"][0]["text"]
