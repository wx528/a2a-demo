from web.v2.models import V2Task, Turn
from web.v2.store import V2Store


def test_roundtrip(tmp_path):
    s = V2Store(str(tmp_path / "v2.db"))
    s.init()
    t = V2Task(id="t1", goal_text="g", created_at=1.0, updated_at=1.0,
               constraints=[{"text": "已有内部 MCP 工具接入", "confirmed": True}],
               materials=[{"name": "现状.md", "text": "内容"}])
    t.turns.append(Turn(id="a", seq=1, stage="clarify", author="ada", kind="statement", title="T", body="B"))
    s.save_task(t)
    got = s.get_task("t1")
    assert got is not None and got.constraints[0].text == "已有内部 MCP 工具接入"
    assert got.turns[0].body == "B" and got.materials[0].name == "现状.md"


def test_list_order_and_missing(tmp_path):
    s = V2Store(str(tmp_path / "v2.db"))
    s.init()
    for i, created in enumerate([1.0, 2.0]):
        s.save_task(V2Task(id=f"t{i}", goal_text="g", created_at=created, updated_at=created))
    assert [x.id for x in s.list_tasks()] == ["t1", "t0"]
    assert s.get_task("nope") is None
    s.delete_task("t0")
    assert s.get_task("t0") is None
