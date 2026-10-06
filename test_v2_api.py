"""V2 REST + SSE API 集成测试：demo 模式全流程（TestClient 驱动 web.main）。"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("V2_DEMO", "1")
    monkeypatch.setenv("V2_DB", str(tmp_path / "v2.db"))
    import importlib
    import web.v2.routes as v2_routes
    # routes 在模块导入时读取 env 建立单例，需先重载 routes 再重载 main 才能生效
    monkeypatch.setenv("V2_DEMO_TURN_DELAY", "0")
    importlib.reload(v2_routes)
    import web.main as m
    importlib.reload(m)
    return TestClient(m.app)


def _create(client, **kw):
    body = dict(
        goal_type="decision",
        goal_text="判断团队是否需要引入 A2A",
        expected_outcome="一份采用建议与试点计划",
        constraints=["已有内部 MCP 工具接入", "首阶段优先私有化", "只验证一个跨团队协作场景"],
    )
    body.update(kw)
    return client.post("/api/v2/tasks", json=body)


def test_create_rejects_unsupported(client):
    r = _create(client, goal_type="research")
    assert r.status_code == 422


def test_full_demo_loop(client):
    r = _create(client)
    assert r.json()["status"] == "preparing"
    tid = r.json()["id"]
    assert client.post(f"/api/v2/tasks/{tid}/start").json()["status"] == "running"
    # 轮询直到 waiting_confirmation（demo 无真实延迟）
    import time
    t = None
    for _ in range(100):
        t = client.get(f"/api/v2/tasks/{tid}").json()
        if t["status"] == "waiting_confirmation":
            break
        time.sleep(0.05)
    assert t["status"] == "waiting_confirmation"
    assert t["demo"] is True
    assert t["connections"] == {k: "demo" for k in ["ada", "turing", "linus", "sage"]}
    did = t["decisions"][0]["id"]
    r2 = client.post(f"/api/v2/tasks/{tid}/decisions/{did}", json={"option_id": "o1"})
    assert r2.json()["status"] == "completed"
    out = client.get(f"/api/v2/tasks/{tid}/outcome").json()
    assert out["label"] == "ai_suggestion"
    ex = client.get(f"/api/v2/tasks/{tid}/export")
    assert ex.status_code == 200 and "演示" in ex.text
    # confirm 接口
    assert client.post(f"/api/v2/tasks/{tid}/outcome/confirm").json()["label"] == "team_confirmed"


def test_sse_stream_emits_init_and_events(client):
    tid = _create(client).json()["id"]
    with client.stream("GET", f"/api/v2/tasks/{tid}/stream") as r:
        assert r.status_code == 200
        buf = b""
        for chunk in r.iter_raw():
            buf += chunk
            if b"event: init" in buf:
                break
        assert b"preparing" in buf


def test_history_and_isolation(client):
    a = _create(client, goal_text="任务A").json()["id"]
    b = _create(client, goal_text="任务B").json()["id"]
    assert a != b
    lst = client.get("/api/v2/tasks").json()
    assert len(lst) == 2
    assert {x["id"] for x in lst} == {a, b}
    # GET 按任务 id 取数：各自载荷的 id/goal_text 与请求的 id 严格对应，不串任务
    ta = client.get(f"/api/v2/tasks/{a}").json()
    tb = client.get(f"/api/v2/tasks/{b}").json()
    assert ta["id"] == a and ta["goal_text"] == "任务A"
    assert tb["id"] == b and tb["goal_text"] == "任务B"
    assert ta["turns"] == [] and tb["turns"] == []


def test_start_publishes_status_change(client, monkeypatch):
    import web.v2.routes as v2_routes

    calls = []
    monkeypatch.setattr(
        v2_routes.broadcaster, "publish", lambda tid, event, data: calls.append((tid, event, data))
    )
    tid = _create(client).json()["id"]
    r = client.post(f"/api/v2/tasks/{tid}/start")
    assert r.status_code == 200
    assert (tid, "status_change", {"status": "running"}) in calls


def test_patch_outcome_ignores_label(client):
    tid = _create(client).json()["id"]
    client.post(f"/api/v2/tasks/{tid}/start")
    client.post(f"/api/v2/tasks/{tid}/end")
    patched = client.patch(
        f"/api/v2/tasks/{tid}/outcome",
        json={"label": "team_confirmed", "conclusion": "x"},
    )
    assert patched.status_code == 200
    out = client.get(f"/api/v2/tasks/{tid}/outcome").json()
    assert out["label"] == "ai_suggestion"
    assert out["conclusion"] == "x"
