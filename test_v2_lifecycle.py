import asyncio
import pytest
from web.v2.models import Ballot, V2Task
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

    async def vote_direction(self, task, seat):
        # 既有用例只关心发言与门：默认全弃权，投票静默跳过
        return Ballot(verdict="abstain")


class VoteBackend(SlowBackend):
    """在 SlowBackend 之上实现 vote_direction：按席位返回固定票。"""

    def __init__(self, ballots=None, fail_seats=()):
        super().__init__()
        self.ballots = ballots or {}
        self.fail_seats = set(fail_seats)

    async def vote_direction(self, task, seat):
        if seat in self.fail_seats:
            raise RuntimeError("vote call down")
        return self.ballots.get(seat, Ballot(verdict="approve", confidence=3, reason="ok"))


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


@pytest.mark.asyncio
async def test_vote_summary_before_gate(tmp_path):
    """review 末、门开前完成投票：事件内容、turn 与 committee_vote 均就位。"""
    backend = VoteBackend({
        "ada": Ballot(verdict="approve", confidence=4, reason="a"),
        "turing": Ballot(verdict="adjust", confidence=3, reason="b"),
        "linus": Ballot(verdict="reject", confidence=2, reason="c"),
        "sage": Ballot(verdict="approve", confidence=4, reason="d"),
    })
    store, orch = _mk(tmp_path, backend)
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    t = store.get_task("t1")
    assert t.status == "waiting_confirmation"
    assert t.committee_vote is not None and t.committee_vote.quorum == 4
    summary = [x for x in t.turns if x.kind == "vote_summary"]
    assert len(summary) == 1 and summary[0].author == "committee"
    gate_index = len(t.turns) - 1  # decision 尚未落 turn；门在投票之后
    assert all(x.kind != "vote_summary" for x in t.turns[:gate_index])


@pytest.mark.asyncio
async def test_vote_runs_once_across_retry(tmp_path):
    """retry 后不重投：committee_vote 已存在即跳过。"""
    backend = VoteBackend({"ada": Ballot(verdict="approve", confidence=4, reason="a"),
                           "turing": Ballot(verdict="approve", confidence=4, reason="b"),
                           "linus": Ballot(verdict="approve", confidence=4, reason="c"),
                           "sage": Ballot(verdict="approve", confidence=4, reason="d")})
    store, orch = _mk(tmp_path, backend)
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    first = store.get_task("t1").committee_vote
    assert first is not None
    # retry 仅接受 failed 任务：门开后标记失败再重试，续跑不得重投
    t = store.get_task("t1")
    t.status = "failed"
    store.save_task(t)
    await asyncio.wait_for(orch.retry("t1"), timeout=5)
    t = store.get_task("t1")
    assert t.committee_vote.ballots == first.ballots  # 未重投（票序与内容不变）
    assert len([x for x in t.turns if x.kind == "vote_summary"]) == 1


@pytest.mark.asyncio
async def test_vote_all_abstain_skips_summary(tmp_path):
    """全部弃权：不生成 committee_vote、无 vote_summary，门照常开。"""
    backend = VoteBackend({s: Ballot(verdict="abstain") for s in ("ada", "turing", "linus", "sage")})
    store, orch = _mk(tmp_path, backend)
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    t = store.get_task("t1")
    assert t.status == "waiting_confirmation" and t.committee_vote is None
    assert not [x for x in t.turns if x.kind == "vote_summary"]
