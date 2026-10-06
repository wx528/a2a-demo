from web.v2 import demo
from web.v2.models import Constraint, Turn, V2Task


def _task(goal=demo.DEMO_GOAL):
    return V2Task(id="t", goal_text=goal, created_at=1.0, updated_at=1.0, demo=True)


def _turn(seq, stage, author, title, body, kind="statement", verified=False):
    return Turn(id=f"turn-{seq}", seq=seq, stage=stage, author=author,
                kind=kind, title=title, body=body, verified=verified)


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


def test_derived_outcome_assembles_real_turns_only():
    t = _task("我们该不该自建机房")
    turns = [
        ("clarify", "ada", "厘清事实", "先核实机房成本与运维现状"),
        ("compare", "turing", "两条路径", "自建与租用各有代价"),
        ("review", "linus", "风险清单", "自建的隐性成本容易被低估"),
        (
            "recommend",
            "sage",
            "建议先租用验证负载",
            "以一个季度为界验证负载曲线，再决定是否自建。",
        ),
    ]
    for i, (stage, author, title, body) in enumerate(turns, start=1):
        t.turns.append(_turn(i, stage, author, title, body))
    t.decisions.append(
        {"id": "d1", "question": demo.DEMO_QUESTION, "options": [
            {"id": "o1", "label": "先租用", "impact": "轻资产起步"}
        ], "chosen_id": "o1", "status": "resolved"}
    )
    t.turns.append(_turn(5, "review", "user", "你已确认：先租用", "轻资产起步",
                         kind="decision_record"))
    t.constraints = [Constraint(text="轻资产起步", confirmed=True)]
    o = demo.build_outcome(t)
    assert o.label == "ai_suggestion"
    assert o.conclusion.startswith("建议先租用验证负载")
    assert "以一个季度为界" in o.conclusion
    assert [r.title for r in o.reasons] == ["厘清事实", "两条路径", "风险清单"]  # 非 Sage 发言
    assert [e.seq_ref for e in o.evidence] == [1, 2, 3, 4, 5]
    assert o.summary_groups.confirmed == ["轻资产起步"]
    # 绝不编造：结构化方案对比/行动项/验收条件留空
    assert o.path_comparison == [] and o.actions == []
    assert o.open_questions == [] and o.acceptance == []


def test_derived_outcome_without_sage_falls_back():
    t = _task("我们该不该自建机房")
    o = demo.build_outcome(t)
    assert o.conclusion == "讨论已完成，建议草稿待整理"
    assert o.reasons == [] and o.evidence == []
