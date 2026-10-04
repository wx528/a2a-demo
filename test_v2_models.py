from web.v2.models import (V2Task, Turn, Decision, DecisionOption, OutcomeDoc, STAGES, STAGE_LABELS)


def _task() -> V2Task:
    return V2Task(id="t1", goal_text="判断团队是否需要引入 A2A", created_at=1.0, updated_at=1.0)


def test_next_seq_empty_and_filled():
    t = _task()
    assert t.next_seq() == 1
    t.turns.append(Turn(id="a", seq=4, stage="clarify", author="ada", kind="statement"))
    assert t.next_seq() == 5


def test_stage_constants():
    assert STAGES == ["clarify", "compare", "review", "recommend"]
    assert STAGE_LABELS["review"] == "评审风险"


def test_defaults():
    t = _task()
    assert t.status == "preparing" and t.current_stage == "clarify"
    assert t.advanced_mode == "pipeline" and t.demo is False
    d = Decision(id="d1", question="q", options=[DecisionOption(id="o1", label="仅内部 Agent", impact="x", recommended=True)])
    assert d.status == "open" and d.round == 1
    o = OutcomeDoc(conclusion="c")
    assert o.label == "ai_suggestion"


def test_public_dict_has_turns_and_demo():
    t = _task()
    t.demo = True
    pub = t.public_dict()
    assert pub["demo"] is True and "turns" in pub and "decisions" in pub
