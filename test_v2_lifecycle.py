import asyncio
import pytest
from web.v2.models import V2Task
from web.v2.store import V2Store
from web.v2.orchestrator import Orchestrator, NullBroadcaster


class SlowBackend:
    def __init__(self, fail_first=False):
        self.calls = 0
        self.fail_first = fail_first

    async def speak(self, task, author, key):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("llm down")
        await asyncio.sleep(0.05)
        return (key, "b", False)


def _mk(tmp_path, backend):
    store = V2Store(str(tmp_path / "db.sqlite"))
    store.init()
    store.save_task(V2Task(id="t1", goal_text="判断团队是否需要引入 A2A", created_at=1.0, updated_at=1.0))
    return store, Orchestrator(store, backend, NullBroadcaster())


@pytest.mark.asyncio
async def test_pause_between_turns_and_resume(tmp_path):
    store, orch = _mk(tmp_path, SlowBackend())
    runner = asyncio.create_task(orch.run_task("t1"))
    await asyncio.sleep(0.02)
    orch.pause("t1")
    await asyncio.wait_for(runner, timeout=5)
    t = store.get_task("t1")
    assert t.status == "paused" and 0 < len(t.turns) < 3
    orch.resume("t1")
    await asyncio.wait_for(asyncio.create_task(orch.run_task("t1")), timeout=5)
    assert store.get_task("t1").status == "waiting_confirmation"


@pytest.mark.asyncio
async def test_failure_marks_failed_then_retry(tmp_path):
    backend = SlowBackend(fail_first=True)
    store, orch = _mk(tmp_path, backend)
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    assert store.get_task("t1").status == "failed"
    assert store.get_task("t1").error
    await asyncio.wait_for(orch.retry("t1"), timeout=5)
    t = store.get_task("t1")
    assert t.status == "waiting_confirmation" and t.error is None


@pytest.mark.asyncio
async def test_intervention_queued_and_acked(tmp_path):
    store, orch = _mk(tmp_path, SlowBackend())
    runner = asyncio.create_task(orch.run_task("t1"))
    ack = await orch.submit_intervention("t1", "补充条件", "首阶段必须私有化")
    assert ack["received"] is True
    await asyncio.wait_for(runner, timeout=5)
    t = store.get_task("t1")
    note = [x for x in t.turns if x.kind == "user_note"]
    assert note and note[0].body == "首阶段必须私有化" and note[0].intent == "补充条件"


@pytest.mark.asyncio
async def test_end_now_completes(tmp_path):
    store, orch = _mk(tmp_path, SlowBackend())
    runner = asyncio.create_task(orch.run_task("t1"))
    await asyncio.sleep(0.01)
    t = await orch.end_now("t1")
    await asyncio.wait_for(runner, timeout=5)
    assert t.status == "completed" and t.outcome is not None


@pytest.mark.asyncio
async def test_real_task_gate_derived_from_goal(tmp_path):
    """非演示任务的决策门必须从目标派生问题/选项，而不是复用演示脚本文案。"""
    from web.v2 import demo

    store, orch = _mk(tmp_path, SlowBackend())
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    t = store.get_task("t1")
    assert t.status == "waiting_confirmation" and t.decisions
    d = t.decisions[0]
    assert d.question != demo.DEMO_QUESTION
    assert "A2A" in d.question
    assert [o.id for o in d.options] == ["o1", "o2", "o3"]
    assert d.options[0].recommended is True
    assert d.options[2].uncertain is True
    assert "演示" not in d.question


@pytest.mark.asyncio
async def test_demo_task_gate_keeps_script(tmp_path):
    """演示任务的决策门仍使用脚本文案（demo 派生成果依赖其选项语义）。"""
    from web.v2 import demo

    store = V2Store(str(tmp_path / "db.sqlite"))
    store.init()
    store.save_task(
        V2Task(id="d1", goal_text="判断团队是否需要引入 A2A", demo=True, created_at=1.0, updated_at=1.0)
    )
    orch = Orchestrator(store, SlowBackend(), NullBroadcaster())
    await asyncio.wait_for(orch.run_task("d1"), timeout=5)
    t = store.get_task("d1")
    assert t.status == "waiting_confirmation"
    assert t.decisions[0].question == demo.DEMO_QUESTION
