# Committee Vote V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** review 末（门开前）由全部 4 席位对「当前讨论方向」独立匿名投票，开票结果消费于讨论流、决策门旁、outcome/export。

**Architecture:** 编排器在 `_step` 的 review 分支里、`_open_gate` 之前插入投票推进单元；票经 `agents_client.vote_direction` 逐席位独立调用（聚合后解析 JSON，不流式发布）；收齐后合成单个 `vote_summary` turn + `task.committee_vote` 字段，一次性发布 `vote_revealed`。匿名在数据层成立（逐票明细不落持久层）。

**Tech Stack:** FastAPI + Pydantic v2（后端）、React + TypeScript（前端）、pytest/TestClient（测试）、uv。

**Spec:** `docs/superpowers/specs/2026-10-11-committee-vote-design.md`

## Global Constraints

- 匿名不变量：收齐前零发布；逐票明细不落 turns/快照/outcome.evidence/export；只有汇总与洗牌后的匿名列表
- 投票永不阻塞流程：单票失败重试 1 次后弃权（`abstain`）；全部弃权 → 不生成 `committee_vote`、不发 `vote_summary`，直接开门
- 全任务仅投一次（`committee_vote` 已存在即跳过）；「暂不确定」重开的门复用同一份票（标注「首轮投票」）
- 投票结果不改变流程（照常开门）
- 中文文案；Windows 下用 Edit/Write 工具改文件（PowerShell 管道毁中文）；测试命令一律 `uv run pytest ...`
- demo 任务零真实调用；`V2_DEMO_TURN_DELAY` 测试中置 0
- 每个任务结束：`uv run ruff check .` 干净 + 相关测试绿 + commit

---

### Task 1: 数据模型与投票纯函数

**Files:**
- Modify: `web/v2/models.py`（Turn.kind 加 `vote_summary`；新增 `Ballot`/`CommitteeVote`；`V2Task.committee_vote` 字段）
- Create: `web/v2/vote.py`（解析/聚合/洗牌/渲染纯函数 + prompt 构造）
- Test: `test_vote.py`

**Interfaces:**
- Produces（后续任务依赖，签名必须一致）:
  - `models.Ballot(verdict: Literal["approve","adjust","reject","abstain"], confidence: int = 0, reason: str = "")`
  - `models.CommitteeVote(tally: dict[str,int], split: Literal["unanimous","majority","split"], ballots: list[Ballot], quorum: int)`
  - `models.Turn.kind` 增加 `"vote_summary"`
  - `models.V2Task.committee_vote: CommitteeVote | None = None`
  - `vote.parse_ballot(text: str) -> Ballot | None`（None=不可解析）
  - `vote.build_vote_prompt(task: V2Task) -> str`（投票指令 prompt 正文，不含身份行）
  - `vote.aggregate(task: V2Task, ballots_by_seat: dict[str, Ballot]) -> CommitteeVote`（洗牌 seed=`task.id`，算 tally/split/quorum；全弃权时 `quorum == 0`）
  - `vote.render_summary(vote: CommitteeVote) -> str`（vote_summary turn 的 body 文本，与前端展示一致：计票 + 「评审 N」匿名票）
  - `vote.REVIEW_VOTE_QUESTION = "是否认可当前讨论方向（可推进到建议整理阶段）？"`

- [ ] **Step 1: 写失败测试** `test_vote.py`

```python
"""Committee vote 纯函数测试：解析 / 聚合 / split / 洗牌确定性。"""

from web.v2 import vote
from web.v2.models import Ballot, CommitteeVote, V2Task


def _task(task_id="t1"):
    return V2Task(id=task_id, goal_text="判断团队是否需要引入 A2A", created_at=1.0, updated_at=1.0)


def test_parse_ballot_plain_json():
    b = vote.parse_ballot('{"verdict": "approve", "confidence": 4, "reason": "与约束一致"}')
    assert b == Ballot(verdict="approve", confidence=4, reason="与约束一致")


def test_parse_ballot_with_fence_and_noise():
    text = '好的，以下是我的票：\n```json\n{"verdict": "reject", "confidence": 2, "reason": "权限面未讨论"}\n```\n以上。'
    assert vote.parse_ballot(text).verdict == "reject"


def test_parse_ballot_invalid_returns_none():
    assert vote.parse_ballot("这不是 JSON") is None
    assert vote.parse_ballot('{"verdict": "maybe"}') is None  # 非法 verdict


def test_aggregate_majority_and_quorum():
    task = _task()
    v = vote.aggregate(task, {
        "ada": Ballot(verdict="approve", confidence=4, reason="r1"),
        "turing": Ballot(verdict="adjust", confidence=3, reason="r2"),
        "linus": Ballot(verdict="reject", confidence=2, reason="r3"),
        "sage": Ballot(verdict="approve", confidence=4, reason="r4"),
    })
    assert v.tally == {"approve": 2, "adjust": 1, "reject": 1}
    assert v.split == "majority" and v.quorum == 4


def test_aggregate_unanimous_and_split():
    unanimous = vote.aggregate(_task(), {s: Ballot(verdict="approve", confidence=5, reason="r") for s in ("ada", "turing", "linus", "sage")})
    assert unanimous.split == "unanimous"
    sp = vote.aggregate(_task(), {
        "ada": Ballot(verdict="approve", confidence=5, reason="r"),
        "turing": Ballot(verdict="adjust", confidence=5, reason="r"),
        "linus": Ballot(verdict="reject", confidence=5, reason="r"),
        "sage": Ballot(verdict="abstain", confidence=0, reason=""),
    })
    assert sp.split == "split" and sp.quorum == 3


def test_aggregate_all_abstain_means_zero_quorum():
    v = vote.aggregate(_task(), {s: Ballot(verdict="abstain") for s in ("ada", "turing", "linus", "sage")})
    assert v.quorum == 0 and v.split == "split"


def test_ballot_order_shuffled_deterministically_by_task_id():
    seats = {s: Ballot(verdict="approve", confidence=i + 1, reason=s) for i, s in enumerate(("ada", "turing", "linus", "sage"))}
    a = vote.aggregate(_task("xyz"), dict(seats))
    b = vote.aggregate(_task("xyz"), dict(seats))
    c = vote.aggregate(_task("other"), dict(seats))
    assert [x.reason for x in a.ballots] == [x.reason for x in b.ballots]
    assert [x.reason for x in a.ballots] != [x.reason for x in c.ballots]  # 不同任务不同序（弱断言：seed 不同）


def test_render_summary_contains_tally_and_anonymous_labels():
    v = vote.aggregate(_task("xyz"), {
        "ada": Ballot(verdict="approve", confidence=4, reason="与约束一致"),
        "turing": Ballot(verdict="abstain"),
        "linus": Ballot(verdict="reject", confidence=2, reason="权限面"),
        "sage": Ballot(verdict="approve", confidence=3, reason="无分歧"),
    })
    text = vote.render_summary(v)
    assert "委员会投票" in text and "赞成 2" in text
    assert "评审 1" in text and "ada" not in text and "turing" not in text  # 匿名


def test_build_vote_prompt_contains_rubric_and_constraints():
    from web.v2.models import Constraint

    task = _task()
    task.constraints = [Constraint(text="首阶段私有化", confirmed=True)]
    prompt = vote.build_vote_prompt(task)
    assert vote.REVIEW_VOTE_QUESTION in prompt
    assert "首阶段私有化" in prompt and "可行性" in prompt
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest test_vote.py -q`
Expected: FAIL（`web.v2.vote` 不存在 / Ballot 未定义）

- [ ] **Step 3: 实现** `web/v2/models.py` 修改

`Turn.kind` 行改为：

```python
    kind: Literal["statement", "user_note", "decision_record", "system", "vote_summary"]
```

文件末尾（`V2Task` 之前）加：

```python
class Ballot(BaseModel):
    verdict: Literal["approve", "adjust", "reject", "abstain"]
    confidence: int = 0
    reason: str = ""


class CommitteeVote(BaseModel):
    tally: dict[str, int]
    split: Literal["unanimous", "majority", "split"]
    ballots: list[Ballot]
    quorum: int
```

`V2Task` 的 `outcome` 字段后加：

```python
    committee_vote: CommitteeVote | None = None
```

- [ ] **Step 4: 实现** `web/v2/vote.py`（新文件）

```python
"""委员会独立投票：解析 / 聚合 / 匿名渲染纯函数（v1）。

匿名不变量：本模块不感知席位名与票的对应关系对外暴露——aggregate 返回的
ballots 已按 task.id 洗牌，调用方只落盘/展示该匿名序列。
"""

import json
import random
import re

from web.v2.models import Ballot, CommitteeVote, V2Task

REVIEW_VOTE_QUESTION = "是否认可当前讨论方向（可推进到建议整理阶段）？"

_VERDICTS = ("approve", "adjust", "reject")
_ANON_LABELS = ("评审 1", "评审 2", "评审 3", "评审 4")
_VERDICT_LABELS = {"approve": "赞成", "adjust": "调整", "reject": "反对", "abstain": "弃权"}


def build_vote_prompt(task: V2Task) -> str:
    """投票指令正文（不含身份行；身份行由 agents_client 注入）。"""
    constraints = "\n".join(
        f"- {'[已确认] ' if c.confirmed else ''}{c.text}" for c in task.constraints
    ) or "（尚无）"
    discussion = "\n".join(
        f"- {t.author}（{t.stage}）：{t.title}" for t in task.turns if t.kind == "statement"
    )
    return (
        f"{REVIEW_VOTE_QUESTION}\n\n"
        f"目标：{task.goal_text}\n\n"
        f"约束：\n{constraints}\n\n"
        f"近期讨论（发言标题）：\n{discussion}\n\n"
        "评判标准：与已确认约束的一致性、可行性、未被讨论的风险。\n"
        '只输出一个 JSON 对象，格式：{"verdict": "approve|adjust|reject", "confidence": 1到5的整数, "reason": "不超过60字的理由"}\n'
        "不要输出其他内容。"
    )


def parse_ballot(text: str) -> Ballot | None:
    """从模型输出中抽取选票 JSON；不可解析或 verdict 非法返回 None。"""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    candidates.extend(re.findall(r"\{[^{}]*\}", text, re.DOTALL))
    for raw in candidates:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("verdict") not in _VERDICTS:
            continue
        try:
            confidence = max(1, min(5, int(data.get("confidence", 3))))
        except Exception:
            confidence = 3
        reason = str(data.get("reason") or "")[:60].strip()
        return Ballot(verdict=data["verdict"], confidence=confidence, reason=reason)
    return None


def aggregate(task: V2Task, ballots_by_seat: dict[str, Ballot]) -> CommitteeVote:
    """聚合并按 task.id 洗牌（确定性）；abstain 不计入 tally。"""
    rng = random.Random(task.id)
    ballots = [ballots_by_seat[seat] for seat in sorted(ballots_by_seat)]
    rng.shuffle(ballots)
    tally = {v: 0 for v in _VERDICTS}
    quorum = 0
    for b in ballots:
        if b.verdict != "abstain":
            tally[b.verdict] += 1
            quorum += 1
    return CommitteeVote(tally=tally, split=_split_of(tally), ballots=ballots, quorum=quorum)


def _split_of(tally: dict[str, int]) -> str:
    counts = sorted(tally.values(), reverse=True)
    if counts[0] == 4:
        return "unanimous"
    if counts[0] >= 2:
        return "majority"
    return "split"


def render_summary(vote_result: CommitteeVote) -> str:
    """vote_summary turn 的 body：计票 + 匿名票（与前端展示一致）。"""
    lines = [f"委员会投票（{_VERDICT_LABELS['approve']} {vote_result.tally['approve']} / "
             f"{_VERDICT_LABELS['adjust']} {vote_result.tally['adjust']} / "
             f"{_VERDICT_LABELS['reject']} {vote_result.tally['reject']}，"
             f"{_SPLIT_LABELS[vote_result.split]}）", ""]
    for i, b in enumerate(vote_result.ballots):
        label = _ANON_LABELS[i % len(_ANON_LABELS)]
        if b.verdict == "abstain":
            lines.append(f"- {label}：弃权")
        else:
            lines.append(f"- {label}：{_VERDICT_LABELS[b.verdict]}（信心 {b.confidence}/5）—— {b.reason}")
    return "\n".join(lines)


_SPLIT_LABELS = {"unanimous": "全票一致", "majority": "多数意见", "split": "意见分裂"}
```

（`_split_of` 采用此简化版——4 票同向 unanimous，最高票 ≥2 majority，否则 split；
重度弃权的角落（如 1 approve + 3 abstain）落 `split`，可接受且由测试覆盖。）

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest test_vote.py -q`
Expected: PASS（9 passed）

- [ ] **Step 6: 回归 + 提交**

```bash
uv run pytest test_v2_models.py test_v2_api.py -q
uv run ruff check .
git add web/v2/models.py web/v2/vote.py test_vote.py
git commit -m "feat(v2): committee vote models and pure functions"
```

---

### Task 2: agents_client.vote_direction + 编排器挂点

**Files:**
- Modify: `web/v2/agents_client.py`（`AgentSpeakerBackend.vote_direction`）
- Modify: `web/v2/orchestrator.py`（`_step` review 分支插 `_run_vote`；`_publish` 复用）
- Test: `test_v2_lifecycle.py`（追加）、`test_v2_agents_client.py`（追加）

**Interfaces:**
- Consumes: Task 1 的 `vote.build_vote_prompt / parse_ballot / aggregate / render_summary`、`models.Ballot/CommitteeVote`
- Produces:
  - `AgentSpeakerBackend.vote_direction(task: V2Task, seat: str) -> Ballot`（内部重试 1 次，失败返回 `Ballot(verdict="abstain")`；demo 任务由编排器短路，不进此方法）
  - `Orchestrator._run_vote(task: V2Task) -> None`：发 `vote_start` → 逐席位收票 → 全弃权则返回（不开票）→ 合成 `vote_summary` turn + `task.committee_vote` + `_save` + 发 `vote_revealed {turn_id, tally, split}` + `turn_done`
  - SSE 事件：`vote_start {author: "committee"}`、`vote_revealed {turn_id, tally, split}`（turn 本体经既有 `turn_done` + REST 快照到达）

- [ ] **Step 1: 写失败测试**（`test_v2_lifecycle.py` 追加；后端 fake 扩展投票能力）

```python
class VoteBackend(SlowBackend):
    """在 SlowBackend 之上实现 vote_direction：按席位返回固定票。"""

    def __init__(self, ballots=None, fail_seats=()):
        super().__init__()
        self.ballots = ballots or {}
        self.fail_seats = set(fail_seats)

    async def vote_direction(self, task, seat):
        from web.v2.models import Ballot
        if seat in self.fail_seats:
            raise RuntimeError("vote call down")
        return self.ballots.get(seat, Ballot(verdict="approve", confidence=3, reason="ok"))
```

追加用例：

```python
@pytest.mark.asyncio
async def test_vote_summary_before_gate(tmp_path):
    """review 末、门开前完成投票：事件内容、turn 与 committee_vote 均就位。"""
    from web.v2.models import Ballot
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
    from web.v2.models import Ballot
    backend = VoteBackend({"ada": Ballot(verdict="approve", confidence=4, reason="a"),
                           "turing": Ballot(verdict="approve", confidence=4, reason="b"),
                           "linus": Ballot(verdict="approve", confidence=4, reason="c"),
                           "sage": Ballot(verdict="approve", confidence=4, reason="d")})
    store, orch = _mk(tmp_path, backend)
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    first = store.get_task("t1").committee_vote
    await asyncio.wait_for(orch.retry("t1"), timeout=5)
    t = store.get_task("t1")
    assert t.committee_vote.ballots == first.ballots  # 未重投（票序与内容不变）
    assert len([x for x in t.turns if x.kind == "vote_summary"]) == 1


@pytest.mark.asyncio
async def test_vote_all_abstain_skips_summary(tmp_path):
    """全部弃权：不生成 committee_vote、无 vote_summary，门照常开。"""
    from web.v2.models import Ballot
    backend = VoteBackend({s: Ballot(verdict="abstain") for s in ("ada", "turing", "linus", "sage")})
    store, orch = _mk(tmp_path, backend)
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    t = store.get_task("t1")
    assert t.status == "waiting_confirmation" and t.committee_vote is None
    assert not [x for x in t.turns if x.kind == "vote_summary"]
```

`test_v2_agents_client.py` 追加（解析重试与弃权，monkeypatch `_stream_text`）：

```python
def test_vote_direction_parses_after_retry():
    """首次输出无 JSON、第二次有效：返回有效票（重试 1 次）。"""
    import asyncio
    from web.v2.agents_client import AgentSpeakerBackend
    from web.v2.models import Ballot, V2Task

    class B(AgentSpeakerBackend):
        def __init__(self, outputs):
            super().__init__(broadcaster=None)
            self.outputs = list(outputs)

        async def _stream_text(self, task, author, url, prompt):
            return self.outputs.pop(0)

    task = V2Task(id="t9", goal_text="g", created_at=1.0, updated_at=1.0)
    b = B(["我觉得还行", '{"verdict": "approve", "confidence": 4, "reason": "ok"}'])
    ballot = asyncio.run(b.vote_direction(task, "ada"))
    assert ballot.verdict == "approve"


def test_vote_direction_abstains_on_garbage():
    import asyncio
    from web.v2.agents_client import AgentSpeakerBackend
    from web.v2.models import V2Task

    class B(AgentSpeakerBackend):
        def __init__(self):
            super().__init__(broadcaster=None)

        async def _stream_text(self, task, author, url, prompt):
            return "还是不行"

    task = V2Task(id="t9", goal_text="g", created_at=1.0, updated_at=1.0)
    ballot = asyncio.run(B().vote_direction(task, "ada"))
    assert ballot.verdict == "abstain"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest test_v2_lifecycle.py test_v2_agents_client.py -q`
Expected: FAIL（`vote_direction` / `committee_vote` 行为不存在）

- [ ] **Step 3: 实现 `agents_client.vote_direction`**

在 `AgentSpeakerBackend` 内追加（复用 `_stream_text` 与 URL 解析模式，与 `speak` 同构）：

```python
    async def vote_direction(self, task: V2Task, seat: str) -> Ballot:
        """对当前讨论方向独立投票：聚合后解析 JSON，失败重试 1 次，再失败弃权。"""
        from web.v2 import vote as vote_mod

        expert = task.expert_by_id(seat)
        url = expert.url if expert else ROLE_AGENTS.get(seat)
        if not url:
            return Ballot(verdict="abstain")
        prompt = (
            (_identity_line(task, seat, f"review_vote_{seat}") + "\n\n")
            + vote_mod.build_vote_prompt(task)
        )
        text = ""
        for _ in range(2):
            try:
                text = await self._stream_text(task, seat, url, prompt)
            except Exception:
                text = ""
            ballot = vote_mod.parse_ballot(text)
            if ballot is not None:
                return ballot
        return Ballot(verdict="abstain")
```

`Ballot` 通过文件顶部 `from web.v2.models import V2Task, Ballot` 导入（按该文件既有导入风格合并）。

- [ ] **Step 4: 实现 `orchestrator._run_vote` 与 `_step` 挂点**

`_step` 的 review 分支改为：

```python
        if stage == "review":
            await self._run_vote(task)
            self._open_gate(task)
            return False
```

`Orchestrator` 内新增（放在 `_open_gate` 之前）：

```python
    async def _run_vote(self, task: V2Task) -> None:
        """门开前的委员会独立投票；全弃权则静默跳过，流程不阻塞。"""
        if task.committee_vote is not None:
            return
        self._publish(task.id, "vote_start", {"author": "committee"})
        from web.v2 import vote as vote_mod
        from web.v2.experts import DEFAULT_ASSIGNMENTS

        if task.demo:
            ballots_by_seat = dict(demo.DEMO_BALLOTS)
        else:
            assignments = task.assignments or DEFAULT_ASSIGNMENTS
            ballots_by_seat = {}
            for seat in assignments.values():  # 四个 purpose 的在任席位（快照）
                ballots_by_seat[seat] = await self.backend.vote_direction(task, seat)
        result = vote_mod.aggregate(task, ballots_by_seat)
        if result.quorum == 0:
            return
        task.committee_vote = result
        turn = self._make_turn(
            task, "review", "committee", "vote_summary",
            title="委员会投票", body=vote_mod.render_summary(result),
        )
        self._save(task)
        self._publish(task.id, "vote_revealed", {
            "turn_id": turn.id,
            "tally": result.tally,
            "split": result.split,
        })
        self._publish(task.id, "turn_done", {"turn_id": turn.id, "seq": turn.seq})
```

注意（实现者须知）：
- 席位取自任务快照 `task.assignments`（purpose→seat；旧任务回退 `DEFAULT_ASSIGNMENTS`），
  与 `_speak` 的 `expert_for` 体系一致；不要用完整 turn key（`clarify_ada`）查席位
- demo 分支的 `demo.DEMO_BALLOTS` 在 Task 3 提供；本任务先在 `demo.py` 放占位常量
  `DEMO_BALLOTS: dict[str, Ballot] = {}` 保证可导入（Task 3 填真值），或把 Task 3 的常量
  一并本任务实现——二选一，保持 `test_v2_lifecycle` 新用例全绿即可
- 投票中 `pause`：`run_task` 循环在 `_step` 内不检查 status——与 `_speak` 相同的既有语义，
  v1 不加新机制（spec §10）

- [ ] **Step 5: 跑测试确认通过**

Run: `uv run pytest test_v2_lifecycle.py test_v2_agents_client.py test_vote.py -q`
Expected: PASS

- [ ] **Step 6: 回归 + 提交**

```bash
uv run pytest test_v2_orchestrator.py test_experts_orchestration.py -q
uv run ruff check .
git add web/v2/agents_client.py web/v2/orchestrator.py web/v2/demo.py test_v2_lifecycle.py test_v2_agents_client.py
git commit -m "feat(v2): committee vote orchestration before gate"
```

---

### Task 3: demo 脚本票

**Files:**
- Modify: `web/v2/demo.py`（`DEMO_BALLOTS` 常量；若 Task 2 已占位则替换为真值）
- Test: `test_v2_demo.py`（追加）

**Interfaces:**
- Produces: `demo.DEMO_BALLOTS: dict[str, Ballot]`（键为席位 id：`ada/turing/linus/sage`）

- [ ] **Step 1: 写失败测试**（`test_v2_demo.py` 追加）

```python
def test_demo_ballots_majority_2_1_1():
    from web.v2 import demo
    from web.v2.models import V2Task
    from web.v2 import vote as vote_mod

    task = V2Task(id="d1", goal_text="g", demo=True, created_at=1.0, updated_at=1.0)
    result = vote_mod.aggregate(task, demo.DEMO_BALLOTS)
    assert result.tally == {"approve": 2, "adjust": 1, "reject": 1}
    assert result.split == "majority" and result.quorum == 4
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest test_v2_demo.py -q`
Expected: FAIL（`DEMO_BALLOTS` 为空/不存在）

- [ ] **Step 3: 实现**（`web/v2/demo.py`，`DEMO_OPTIONS` 之后）

```python
# 委员会独立投票脚本票（demo 专用，2:1:1 majority，与 goal 无关、确定性）
DEMO_BALLOTS: dict[str, "Ballot"] = {
    "ada": Ballot(verdict="approve", confidence=4, reason="方向与已确认约束一致"),
    "turing": Ballot(verdict="adjust", confidence=3, reason="建议补一个可观测的验收口径"),
    "linus": Ballot(verdict="reject", confidence=2, reason="试点边界外仍有未讨论的权限面"),
    "sage": Ballot(verdict="approve", confidence=4, reason="各阶段证据无根本分歧"),
}
```

（`Ballot` 加入该文件既有的 `from web.v2.models import (...)` 导入列表。）

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest test_v2_demo.py test_v2_lifecycle.py -q`
Expected: PASS（demo 生命周期里 `task.demo` 走 `DEMO_BALLOTS`，既有 demo 全流程用例仍绿）

- [ ] **Step 5: 提交**

```bash
uv run ruff check .
git add web/v2/demo.py test_v2_demo.py
git commit -m "feat(v2): demo committee ballots 2:1:1"
```

---

### Task 4: 前端——投票指示、vote_summary 渲染、门旁计票条

**Files:**
- Modify: `web/frontend/src/lib/v2api.ts`（`TurnKind` 加 `"vote_summary"`；`V2TaskT.committee_vote`；`BallotT`/`CommitteeVoteT` 类型）
- Modify: `web/frontend/src/hooks/useV2Stream.ts`（`vote_start` 尾部指示；`vote_revealed` 触发 refresh）
- Modify: `web/frontend/src/components/v2/TurnCard.tsx`（`vote_summary` 渲染分支）
- Modify: `web/frontend/src/components/v2/DecisionGate.tsx`（计票 mini 条 + split 徽标）
- Test: 无组件测试基建——以 `npm run lint` + `npm run build` + Task 6 人工/脚本 E2E 为验收

**Interfaces:**
- Consumes: 后端事件 `vote_start {author}`、`vote_revealed {turn_id, tally, split}`；快照 `task.committee_vote`；turn `kind="vote_summary"`
- Produces: `v2api.BallotT { verdict: "approve"|"adjust"|"reject"|"abstain"; confidence: number; reason: string }`、`CommitteeVoteT { tally: Record<string, number>; split: "unanimous"|"majority"|"split"; ballots: BallotT[]; quorum: number }`

- [ ] **Step 1: 类型**（`v2api.ts`）

```ts
export type TurnKindT = "statement" | "user_note" | "decision_record" | "system" | "vote_summary"

export interface BallotT {
  verdict: "approve" | "adjust" | "reject" | "abstain"
  confidence: number
  reason: string
}

export interface CommitteeVoteT {
  tally: Record<string, number>
  split: "unanimous" | "majority" | "split"
  ballots: BallotT[]
  quorum: number
}
```

（`TurnKindT` 若该文件已内联 union 于 `TurnT.kind`，直接在原 union 上追加 `"vote_summary"`；`V2TaskT` 加 `committee_vote: CommitteeVoteT | null`。）

- [ ] **Step 2: useV2Stream**——仿照 `turn_start`（:150）与 `decision_required`（:208）的监听写法：

```ts
source.addEventListener("vote_start", (event) => {
  setThinkingAuthor("committee")   // 复用尾部指示行，「委员会投票中…」文案在渲染层判断
})
source.addEventListener("vote_revealed", () => {
  setThinkingAuthor(null)
  void refresh()
})
```

（具体 setter 名以该文件现状为准；`turn_done`/既有 refresh 机制若已覆盖快照更新，
`vote_revealed` 只需清除指示。尾部指示行文案：`thinkingAuthor === "committee"` 时渲染
「委员会投票中…」，普通席位仍渲染「{author} 思考中…」。）

- [ ] **Step 3: TurnCard `vote_summary` 分支**——按该文件既有 `kind` 分支风格新增：

```tsx
if (turn.kind === "vote_summary") {
  return (
    <article className="rounded-[12px] border border-border bg-card p-4">
      <header className="flex items-center gap-2">
        <Vote className="size-4 text-primary" aria-hidden />
        <span className="text-sm font-bold text-foreground">委员会投票</span>
        <span className="rounded-md bg-accent px-2 py-0.5 text-xs text-primary">匿名</span>
      </header>
      <VoteTallyBody body={turn.body} />
    </article>
  )
}
```

（`VoteTallyBody`：把 turn.body 按行拆分，首行计票加粗、`- 评审 N：` 行渲染为票卡列表；
`lucide-react` 的 `Vote` 图标已在依赖内。实现保持与 TurnCard 既有 statement 分支相同的
className/FOCUS_RING 风格。）

- [ ] **Step 4: DecisionGate 计票条**——组件加可选 prop `committeeVote?: CommitteeVoteT | null`（WorkspacePage 已持有 task，传入 `task.committee_vote`）：

```tsx
{committeeVote && committeeVote.quorum > 0 ? (
  <div className="flex flex-col gap-1.5 rounded-lg bg-panel p-3">
    <div className="flex h-2 overflow-hidden rounded-full bg-border" role="img"
         aria-label={`委员会投票：赞成 ${committeeVote.tally.approve ?? 0}，调整 ${committeeVote.tally.adjust ?? 0}，反对 ${committeeVote.tally.reject ?? 0}`}>
      <span className="bg-emerald-500" style={{ width: `${pct("approve")}%` }} />
      <span className="bg-amber-500" style={{ width: `${pct("adjust")}%` }} />
      <span className="bg-rose-500" style={{ width: `${pct("reject")}%` }} />
    </div>
    <span className="text-xs text-muted-foreground">
      委员会投票 · {SPLIT_LABELS[committeeVote.split]}
    </span>
  </div>
) : null}
```

（`pct = (k) => quorum ? Math.round((tally[k] ?? 0) / quorum * 100) : 0`；
`SPLIT_LABELS = { unanimous: "全票一致", majority: "多数意见", split: "意见分裂" }`；
第二轮门由调用方标注「首轮投票」——WorkspacePage 对 `decisions.length > 1` 时在标签后追加。）

- [ ] **Step 5: 验证 + 提交**

```bash
cd web/frontend && npm run lint && npm run build
git add web/frontend/src
git commit -m "feat(v2): committee vote UI - indicator, summary card, gate tally"
```

---

### Task 5: outcome/export 集成

**Files:**
- Modify: `web/v2/routes.py`（`_export_markdown` :501 追加投票节）
- Modify: `web/frontend/src/pages/OutcomeOverview.tsx`（`committee_vote` 区块）
- Test: `test_v2_api.py`（追加 export 断言）

**Interfaces:**
- Consumes: `task.committee_vote`（REST 快照已自动携带——`public_dict` 用 `model_dump`）

- [ ] **Step 1: 写失败测试**（`test_v2_api.py` 追加到既有 full-loop 用例之后）

```python
def test_export_contains_committee_vote(client):
    tid = _create(client).json()["id"]
    client.post(f"/api/v2/tasks/{tid}/start")
    for _ in range(60):
        t = client.get(f"/api/v2/tasks/{tid}").json()
        if t["status"] == "waiting_confirmation":
            break
        import time as _t; _t.sleep(0.05)
    did = t["decisions"][0]["id"]
    client.post(f"/api/v2/tasks/{tid}/decisions/{did}", json={"option_id": "o1"})
    for _ in range(60):
        t = client.get(f"/api/v2/tasks/{tid}").json()
        if t["status"] in ("completed", "failed"):
            break
        import time as _t; _t.sleep(0.05)
    assert t["status"] == "completed"
    assert t["committee_vote"] is not None and t["committee_vote"]["quorum"] == 4
    exported = client.get(f"/api/v2/tasks/{tid}/export").text
    assert "委员会投票" in exported and "评审" in exported
```

（若既有 full-loop helper 已封装驱动，直接复用其 helper；以上为独立完整写法。）

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest test_v2_api.py::test_export_contains_committee_vote -q`
Expected: FAIL（export 无「委员会投票」节）

- [ ] **Step 3: 实现 export 节**（`routes.py` `_export_markdown`，在决策/结论节之后）

```python
    if task.committee_vote is not None:
        from web.v2.vote import render_summary
        lines += ["", "## 委员会投票", "", render_summary(task.committee_vote)]
```

- [ ] **Step 4: OutcomeOverview 区块**——按该文件既有 section 模式（与「已确认约束/分歧/待验证」并列）新增「委员会投票」卡：计票三段条 + split 标签 + `ballots` 匿名列表（复用 TurnCard 的展示语义即可，允许内联简单渲染）。`OutcomePage` 无需改动（Overview 自动携带新 section）。

- [ ] **Step 5: 验证 + 提交**

```bash
uv run pytest test_v2_api.py -q
cd web/frontend && npm run lint && npm run build
uv run ruff check .
git add web/v2/routes.py web/frontend/src test_v2_api.py
git commit -m "feat(v2): committee vote in outcome and export"
```

---

### Task 6: 全量回归 + 收尾验收

**Files:**
- 无新增；全量验证与收尾

- [ ] **Step 1: 全量后端**

```bash
uv run pytest -q
```
Expected: 全绿（既有 155+ + 本特性新增 ~15）

- [ ] **Step 2: 静态检查与前端构建**

```bash
uv run ruff check .
cd web/frontend && npm run lint && npm run build
```

- [ ] **Step 3: demo E2E 冒烟（本地）**

```bash
uv run python - <<'PY'
import os, time, httpx
os.environ.setdefault("V2_DB", "data/v2_vote_smoke.db")
import web.main  # noqa
PY
```

（实现者可改用与 `test_v2_api.py::test_full_demo_loop` 相同的 TestClient 驱动；
验收点：SSE 事件序 `vote_start → vote_revealed → decision_required`、
快照含 `committee_vote{2,1,1, majority}`、export 含投票节。）

- [ ] **Step 4: 台账 + 提交**

在 `.superpowers/sdd/progress.md`（worktree 内）记录 6 任务结论与 minors；
最终提交：

```bash
git add -A
git commit -m "chore(v2): committee vote ledger and verification"
```

收尾走 finishing-a-development-branch（本地 merge main → 重建生产栈 → push，无 PR）。
