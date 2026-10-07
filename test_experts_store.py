import pytest
from web.v2.experts import (BUILTIN_EXPERTS, DEFAULT_ASSIGNMENTS, PURPOSES, V2ExpertStore)


def test_defaults_and_builtins():
    assert PURPOSES == ["research", "propose", "challenge", "synthesize"]
    assert DEFAULT_ASSIGNMENTS == {"research": "ada", "propose": "turing", "challenge": "linus", "synthesize": "sage"}
    assert len(BUILTIN_EXPERTS) == 4
    ada = next(e for e in BUILTIN_EXPERTS if e.id == "ada")
    assert ada.source == "builtin" and "研究" in ada.tags and ada.emoji == "🧬"


def test_crud_and_builtin_protection(tmp_path):
    s = V2ExpertStore(str(tmp_path / "db.sqlite"))
    s.init()
    ids = [e.id for e in s.list_experts()]
    assert set(ids) >= {"ada", "turing", "linus", "sage"}
    s.init()  # 幂等
    assert len(s.list_experts()) == 4
    with pytest.raises(ValueError):
        s.delete_expert("ada")
    from web.v2.experts import Expert
    s.create_expert(Expert(id="hermes1", name="Hermes", url="http://x:9", tags=["设计"]))
    assert s.get_expert("hermes1").name == "Hermes"
    s.update_expert("hermes1", {"enabled": False, "tags": ["设计", "权衡"]})
    assert s.get_expert("hermes1").enabled is False and len(s.get_expert("hermes1").tags) == 2
    s.delete_expert("hermes1")
    assert s.get_expert("hermes1") is None


def test_task_snapshot_fields():
    from web.v2.models import TaskExpert, V2Task
    t = V2Task(id="t", goal_text="g", created_at=1.0, updated_at=1.0)
    assert t.experts == [] and t.assignments == {}
    t.experts.append(TaskExpert(id="ada", name="研究员 · Ada", url="http://r:8011", emoji="🧬", purpose="research", source="builtin"))
    t.assignments = {"research": "ada"}
    assert t.expert_by_id("ada").purpose == "research"
    assert t.expert_by_id("nope") is None
    pub = t.public_dict()
    assert "experts" in pub and "assignments" in pub
