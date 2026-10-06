import asyncio
import pytest
from web.v2.models import V2Task
from web.v2.store import V2Store
from web.v2.orchestrator import Orchestrator, SpeakerBackend, NullBroadcaster


class EchoBackend(SpeakerBackend):
    async def speak(self, task, author, key):
        await asyncio.sleep(0)
        return (key, f"body:{key}:{task.goal_text}", False)


def _mk(tmp_path, goal="判断团队是否需要引入 A2A"):
    store = V2Store(str(tmp_path / "db.sqlite"))
    store.init()
    t = V2Task(id="t1", goal_text=goal, expected_outcome="一份采用建议与试点计划",
               constraints=[{"text": c} for c in ["已有内部 MCP 工具接入", "首阶段优先私有化",
                                                  "只验证一个跨团队协作场景"]],
               created_at=1.0, updated_at=1.0)
    store.save_task(t)
    orch = Orchestrator(store, EchoBackend(), NullBroadcaster())
    return store, orch, t


async def _drain(coro):
    await asyncio.wait_for(coro, timeout=5)


@pytest.mark.asyncio
async def test_auto_advance_to_gate(tmp_path):
    store, orch, t = _mk(tmp_path)
    await _drain(orch.run_task("t1"))
    t = store.get_task("t1")
    assert t.status == "waiting_confirmation"
    assert t.current_stage == "review"
    assert [x.author for x in t.turns] == ["ada", "turing", "linus"]
    assert [x.seq for x in t.turns] == [1, 2, 3]
    d = t.decisions[0]
    assert d.status == "open" and d.options[0].recommended


@pytest.mark.asyncio
async def test_confirm_completes_task(tmp_path):
    store, orch, t = _mk(tmp_path)
    await _drain(orch.run_task("t1"))
    d = store.get_task("t1").decisions[0]
    await _drain(orch.submit_decision("t1", d.id, "o1"))
    t = store.get_task("t1")
    assert t.status == "completed" and t.current_stage == "recommend"
    assert t.decisions[0].chosen_id == "o1"
    kinds = [(x.author, x.kind) for x in t.turns]
    assert ("user", "decision_record") in kinds and ("sage", "statement") in kinds
    assert any(c.confirmed and c.text == "仅内部 Agent" for c in t.constraints)
    assert t.outcome is not None


@pytest.mark.asyncio
async def test_uncertain_round_then_regate(tmp_path):
    store, orch, t = _mk(tmp_path)
    await _drain(orch.run_task("t1"))
    d1 = store.get_task("t1").decisions[0]
    await _drain(orch.submit_decision("t1", d1.id, "o3"))
    t = store.get_task("t1")
    assert t.status == "waiting_confirmation"
    assert len(t.decisions) == 2 and t.decisions[1].round == 2
    assert t.decisions[0].chosen_id == "o3"  # 记录在案但不是批准


@pytest.mark.asyncio
async def test_submit_idempotent(tmp_path):
    store, orch, t = _mk(tmp_path)
    await _drain(orch.run_task("t1"))
    d = store.get_task("t1").decisions[0]
    await _drain(orch.submit_decision("t1", d.id, "o1"))
    before = len(store.get_task("t1").turns)
    await _drain(orch.submit_decision("t1", d.id, "o2"))  # 已 resolved，忽略
    assert len(store.get_task("t1").turns) == before


@pytest.mark.asyncio
async def test_resolve_decision_sync_then_continue(tmp_path):
    store, orch, t = _mk(tmp_path)
    await _drain(orch.run_task("t1"))
    d = store.get_task("t1").decisions[0]
    resolved = orch.resolve_decision("t1", d.id, "o1")
    assert resolved.status == "running"  # 同步落盘即可返回，不等发言
    mid = store.get_task("t1")
    assert mid.decisions[0].status == "resolved" and mid.outcome is None
    await _drain(orch.continue_after_decision("t1"))
    done = store.get_task("t1")
    assert done.status == "completed" and done.outcome is not None


@pytest.mark.asyncio
async def test_continue_after_decision_noop_when_complete(tmp_path):
    store, orch, t = _mk(tmp_path)
    await _drain(orch.run_task("t1"))
    d = store.get_task("t1").decisions[0]
    await _drain(orch.submit_decision("t1", d.id, "o1"))
    before = len(store.get_task("t1").turns)
    await _drain(orch.continue_after_decision("t1"))  # 已走完，不重复发言
    assert len(store.get_task("t1").turns) == before


@pytest.mark.asyncio
async def test_single_coroutine_guard(tmp_path):
    store, orch, t = _mk(tmp_path)
    task1 = asyncio.create_task(orch.run_task("t1"))
    await asyncio.create_task(orch.run_task("t1"))  # 第二次应立即返回
    await _drain(task1)
    assert store.get_task("t1").status == "waiting_confirmation"
    assert len(store.get_task("t1").turns) == 3
