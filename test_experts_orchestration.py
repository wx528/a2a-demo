import asyncio
import pytest
from web.v2.experts import Expert, V2ExpertStore, resolve_assignments
from web.v2.agents_client import build_turn_prompt
from web.v2.models import TaskExpert, V2Task


def test_resolve_assignments_fallback_and_snapshot(tmp_path):
    s = V2ExpertStore(str(tmp_path / "db.sqlite"))
    s.init()
    s.create_expert(Expert(id="h1", name="Hermes", url="http://x:9", tags=["挑战"]))
    experts, asg = resolve_assignments({"challenge": "h1", "research": "ghost"}, s)
    assert asg["challenge"] == "h1" and asg["research"] == "ada"  # 未知专家回退默认
    assert asg["propose"] == "turing" and asg["synthesize"] == "sage"
    ids = {e.id for e in experts}
    assert {"h1", "ada", "turing", "sage"} <= ids
    assert all(e.purpose for e in experts)


def _task_with_guest():
    t = V2Task(id="t", goal_text="g", created_at=1.0, updated_at=1.0)
    t.experts = [TaskExpert(id="h1", name="Hermes", url="http://x:9", emoji="🔌", purpose="challenge", source="custom"),
                 TaskExpert(id="ada", name="研究员 · Ada", url="http://r:1", emoji="🧬", purpose="research", source="builtin")]
    t.assignments = {"research": "ada", "propose": "turing", "challenge": "h1", "synthesize": "sage"}
    return t


def test_guest_prompt_has_no_persona():
    p = build_turn_prompt(_task_with_guest(), "h1", "review_linus")
    assert "特邀专家" in p and "挑战者" not in p and "Linus" not in p
    assert "[你的任务]" in p and "检查风险与隐含假设" in p


def test_builtin_prompt_keeps_persona():
    p = build_turn_prompt(_task_with_guest(), "ada", "clarify_ada")
    assert "研究员" in p


@pytest.mark.asyncio
async def test_backend_uses_snapshot_url_for_guest(monkeypatch):
    from web.v2.agents_client import AgentSpeakerBackend

    captured = {}

    class FakeClient:
        def __init__(self, url):
            captured["url"] = url

        async def stream_deltas(self, text):
            yield "标题行"
            yield "\n正文内容"

    monkeypatch.setattr("web.v2.agents_client.A2AJSONRPCClient", FakeClient)
    be = AgentSpeakerBackend(NullBroadcasterStub())
    title, body, verified = await be.speak(_task_with_guest(), "h1", "review_linus")
    assert captured["url"] == "http://x:9"
    assert title == "标题行" and body == "正文内容"


class NullBroadcasterStub:
    def publish(self, *args, **kwargs):
        pass


@pytest.mark.asyncio
async def test_orchestrator_uses_assignment(tmp_path):
    from web.v2.orchestrator import Orchestrator, NullBroadcaster
    from web.v2.store import V2Store

    seen = []

    class ProbeBackend:
        async def speak(self, task, author, key):
            seen.append((key, author))
            return (key, "b", False)

    store = V2Store(str(tmp_path / "db.sqlite"))
    store.init()
    t = _task_with_guest()
    t.id = "t1"
    t.status = "preparing"
    store.save_task(t)
    orch = Orchestrator(store, ProbeBackend(), NullBroadcaster())
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    assert ("review_linus", "h1") in seen and ("clarify_ada", "ada") in seen
