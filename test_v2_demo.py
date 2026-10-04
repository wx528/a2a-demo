from web.v2 import demo
from web.v2.models import V2Task


def _task(goal=demo.DEMO_GOAL):
    return V2Task(id="t", goal_text=goal, created_at=1.0, updated_at=1.0, demo=True)


def test_demo_enabled(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("V2_DEMO", raising=False)
    assert demo.demo_enabled() is True
    monkeypatch.setenv("V2_DEMO", "0")
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    assert demo.demo_enabled() is False


def test_scripted_content_anchors():
    t = _task()
    title, body, verified = demo.statement("review_linus", t)
    assert "授权" in body and verified is False
    assert demo.DEMO_OPTIONS[0]["recommended"] is True
    assert demo.DEMO_OPTIONS[2]["uncertain"] is True
    o = demo.build_outcome(t)
    assert o.conclusion.startswith("建议开展内部小范围试点")
    assert len(o.actions) == 3 and o.actions[0].assignee == "待分配"
    assert any("任务交接可追踪" in a for a in [c.title for c in o.acceptance])


def test_parameterized_template_is_deterministic():
    t = _task("我们该不该自建机房")
    a1 = demo.statement("clarify_ada", t)
    a2 = demo.statement("clarify_ada", t)
    assert a1 == a2 and "自建机房" in a1[1]
