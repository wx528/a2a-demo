"""专家注册表 API 测试：CRUD + 探活（TestClient 驱动 web.main）。"""

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


def test_register_requires_reachable_card(client, monkeypatch):
    import web.v2.routes as r
    monkeypatch.setattr(r, "_probe_expert", lambda url: (False, "ConnectError"))
    resp = client.post("/api/v2/experts", json={"name": "Hermes", "url": "http://x:9", "tags": ["设计"]})
    assert resp.status_code == 422 and "无法连通" in resp.json()["detail"]


def test_register_list_patch_delete(client, monkeypatch):
    import web.v2.routes as r
    monkeypatch.setattr(r, "_probe_expert", lambda url: (True, ""))
    ok = client.post("/api/v2/experts", json={"name": "Hermes", "url": "http://x:9", "tags": ["设计"]})
    assert ok.status_code == 200
    eid = ok.json()["id"]
    assert ok.json()["probe"] == "up" and ok.json()["source"] == "custom"
    lst = client.get("/api/v2/experts").json()
    assert any(e["id"] == eid for e in lst) and any(e["id"] == "ada" for e in lst)
    assert client.patch(f"/api/v2/experts/{eid}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"/api/v2/experts/{eid}").status_code == 200
    assert client.delete("/api/v2/experts/ada").status_code == 409
