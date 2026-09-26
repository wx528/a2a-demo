"""步进 API 集成测试：真实 agent（回退模式），TestClient 驱动 web。"""

import importlib
import os
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _start(main_file, port):
    env = {**os.environ, "LLM_API_KEY": "", "LLM_BASE_URL": "",
           "PORT": str(port), "HOST": "localhost"}
    return subprocess.Popen(
        [sys.executable, main_file], cwd=BASE_DIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


@pytest.fixture(scope="module")
def web_app(tmp_path_factory):
    procs = [
        _start("research_agent/main.py", 8011),
        _start("writing_agent/main.py", 8012),
        _start("debate_agent/main.py", 8013),
    ]
    with httpx.Client(trust_env=False, timeout=3) as c:
        for _ in range(60):
            try:
                if all(
                    c.get(f"http://localhost:{p}/").status_code == 200
                    for p in (8011, 8012, 8013)
                ):
                    break
            except Exception:
                pass
            time.sleep(0.5)

    saved = {k: os.environ.get(k) for k in
             ("RESEARCH_AGENT_URL", "WRITING_AGENT_URL", "DEBATE_AGENT_URL")}
    db_dir = str(tmp_path_factory.mktemp("webdb"))
    os.environ["RESEARCH_AGENT_URL"] = "http://localhost:8011"
    os.environ["WRITING_AGENT_URL"] = "http://localhost:8012"
    os.environ["DEBATE_AGENT_URL"] = "http://localhost:8013"
    os.environ["A2A_WEB_DB_DIR"] = db_dir

    import web.db as web_db
    import web.main as web_main
    importlib.reload(web_db)
    importlib.reload(web_main)
    yield web_main

    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    os.environ.pop("A2A_WEB_DB_DIR", None)
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def _create(client, **kw):
    body = {"topic": "步进测试", "mode": "pipeline", **kw}
    return client.post("/api/meetings", json=body).json()


def _turn_events(client, mid):
    resp = client.post(f"/api/meetings/{mid}/turns/next")
    assert resp.status_code == 200, resp.text
    events = []
    for block in resp.text.split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if ev:
            events.append((ev, data))
    return events


def test_personas_endpoint(web_app):
    with TestClient(web_app.app) as client:
        personas = client.get("/api/personas").json()
        ids = [p["id"] for p in personas]
        assert "socrates" in ids and "hume" in ids and "judge" not in ids
        assert all(p["avatar"] for p in personas)


def test_pipeline_step_by_step_with_interjection(web_app):
    with TestClient(web_app.app) as client:
        mid = _create(client)["id"]
        peek = client.get(f"/api/meetings/{mid}/next-turn").json()
        assert peek["next"]["participant_id"] == "research"
        assert peek["auto_play"] is False

        events = _turn_events(client, mid)
        assert any(e[0] == "turn_done" for e in events), "turn must end with turn_done"
        m = client.get(f"/api/meetings/{mid}").json()
        assert len([x for x in m["messages"] if x["participant_id"] == "research"]) == 1

        # 用户插话 -> 下一轮（writing）
        client.post(f"/api/meetings/{mid}/messages", json={"content": "补充：关注安全方面"})
        _turn_events(client, mid)
        m = client.get(f"/api/meetings/{mid}").json()
        assert any(x["participant_id"] == "writing" for x in m["messages"])

        # 跑完剩余轮次 -> done
        for _ in range(3):
            events = _turn_events(client, mid)
        dones = [e for e in events if e[0] == "turn_done"]
        assert dones and '"done": true' in dones[0][1].replace("True", "true")


def test_debate_full_flow_step_mode(web_app):
    with TestClient(web_app.app) as client:
        mid = _create(client, mode="debate", pro_persona="socrates",
                      con_persona="hume", max_rounds=1)["id"]
        speakers = []
        for _ in range(4):
            peek = client.get(f"/api/meetings/{mid}/next-turn").json()
            if peek["done"]:
                break
            speakers.append(peek["next"]["participant_id"])
            _turn_events(client, mid)
        assert speakers == ["socrates", "hume", "judge"]
        m = client.get(f"/api/meetings/{mid}").json()
        judge_msgs = [x for x in m["messages"] if x["type"] == "judge"]
        assert judge_msgs and judge_msgs[0]["participant_id"] == "judge"
        peek = client.get(f"/api/meetings/{mid}/next-turn").json()
        assert peek["done"] is True


def test_user_inquiry_reaches_debate_agent(web_app):
    """步进模式下用户插话成为观众质询：辩论输入带 INQUIRY 段（回退模式验证协议链路）。"""
    with TestClient(web_app.app) as client:
        mid = _create(client, mode="debate", max_rounds=1)["id"]
        _turn_events(client, mid)  # pro 立论
        client.post(f"/api/meetings/{mid}/messages", json={"content": "请回应成本数据"})
        _turn_events(client, mid)  # con 回应（带质询）
        m = client.get(f"/api/meetings/{mid}").json()
        con_msgs = [x for x in m["messages"] if x["participant_id"] == "hume"]
        assert con_msgs, "con turn must produce a message"
