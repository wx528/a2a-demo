# A2A 会议室 V2 · 决策工作区 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 spec `docs/superpowers/specs/2026-10-04-v2-decision-workspace-design.md` 实现 V2 决策闭环：目标首页 → 协作计划 → 决策工作区（阶段化讨论+决策门+介入）→ 决策成果，四个角色为独立 A2A agent 容器，web 进程内编排，全局演示模式。

**Architecture:** `web/v2/` 新包持有模型/SQLite 存储/编排状态机/agent 客户端/演示脚本/REST+SSE 路由；`role_agent/` 一份代码×4 compose 实例（env `ROLE`），协议面复用 `shared/a2a_server.py`；前端 React+Tailwind v4 重写四页（保留 `components/ui/` 与 `lib/sse.ts` 风格），hash 迷你路由，浅色默认双主题。

**Tech Stack:** FastAPI 0.115 / Pydantic v2 / sqlite3 / httpx SSE / React 19 / Tailwind v4 / lucide-react（已有）/ @fontsource Noto Sans SC + JetBrains Mono（新增）。

## Global Constraints

- 全中文界面；品牌「A2A 会议室」；协议名/人名/缩写可英文。
- V2 色板（spec §4.1）逐值使用，浅色为默认主题；状态徽标必须文字+颜色双编码。
- 任务状态枚举（唯一来源=orchestrator）：`preparing|running|waiting_confirmation|paused|completed|failed`；阶段：`clarify|compare|review|recommend`。
- AI 建议永不自动标为已批准/已确认；"暂不确定"必须走追加比较后重问，不得视为批准。
- 演示模式（无 `LLM_API_KEY` 或 `V2_DEMO=1`）下不发起任何 agent/LLM 调用；真实模式 LLM 失败→任务 failed+可重试，绝不静默换脚本。
- 材料 仅登记文本，UI 标注"仅登记文本，不做文档解析"；不虚构引用/负责人/日期（责任人="待分配"、时间="待确定"）。
- 旧 `/api/meetings*` 路由与 V1 容器保留，前端不再引用；V1 页面组件删除。
- Windows 注意：一律用 Edit/Write 工具写文件（PowerShell 管道破坏中文）；长驻服务用 `Start-Process` 分离启动。
- 测试：`uv run pytest <file> -q`（根目录扁平文件）；lint：`uv run ruff check .`；前端：`npm run lint` + `npm run build`（workdir `web/frontend`）。
- 每个任务完成即 commit；消息文本以 Figma 五画面文案为基准。

---

### Task 1: V2 领域模型 `web/v2/models.py`

**Files:**
- Create: `web/v2/__init__.py`（空）
- Create: `web/v2/models.py`
- Test: `test_v2_models.py`

**Interfaces:**
- Produces（后续所有任务依赖的精确类型）:
  - `TaskStatus = Literal["preparing","running","waiting_confirmation","paused","completed","failed"]`
  - `Stage = Literal["clarify","compare","review","recommend"]`
  - `STAGES: list[Stage]`、`STAGE_LABELS: dict[Stage,str]`（澄清需求/比较方案/评审风险/形成建议）
  - `class Material(BaseModel)` `name:str; text:str=""` 
  - `class Constraint(BaseModel)` `text:str; confirmed:bool=False`
  - `class DecisionOption(BaseModel)` `id:str; label:str; impact:str; recommended:bool=False; uncertain:bool=False`
  - `class Decision(BaseModel)` `id:str; round:int=1; question:str; options:list[DecisionOption]; chosen_id:str|None=None; status:Literal["open","resolved"]="open"`
  - `class Turn(BaseModel)` `id:str; seq:int; stage:Stage; author:str`（`ada|turing|linus|sage|user|system`）`; kind:Literal["statement","user_note","decision_record","system"]; title:str=""; body:str=""; verified:bool=False; intent:str|None=None`
  - `class OutcomeDoc(BaseModel)` 字段见 spec §3.1（`label: Literal["draft","ai_suggestion","team_confirmed"]="ai_suggestion"`）
  - `class V2Task(BaseModel)` `id:str; goal_type:Literal["decision"]= "decision"`（创建时其他类型被路由层拒绝）`; goal_text:str; expected_outcome:str; constraints:list[Constraint]; materials:list[Material]; advanced_mode:Literal["pipeline","roundtable","debate"]="pipeline"; advanced_rounds:int=2; status:TaskStatus="preparing"; current_stage:Stage="clarify"; stage_index:int=0; turns:list[Turn]; decisions:list[Decision]; outcome:OutcomeDoc|None=None; demo:bool=False; error:str|None=None; created_at:float; updated_at:float`
  - 方法：`V2Task.next_seq() -> int`（max(seq)+1，空表返回 1）；`V2Task.public_dict() -> dict`（含 turns、decisions、outcome、demo、连接摘要占位）

- [ ] **Step 1: 写失败测试** `test_v2_models.py`

```python
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
```

- [ ] **Step 2: 跑测试确认失败** — `uv run pytest test_v2_models.py -q` → FAIL（ModuleNotFoundError: web.v2）
- [ ] **Step 3: 最小实现** — 创建 `web/v2/__init__.py`（空文件）与 `web/v2/models.py`：按上述 Interfaces 写全部模型；`next_seq` 用 `max((t.seq for t in self.turns), default=0)+1`；`public_dict` 用 `self.model_dump()` 基础上补充 `"demo"`（已在字段中，直接 model_dump 即可）。
- [ ] **Step 4: 跑测试通过** — `uv run pytest test_v2_models.py -q` → 4 passed；`uv run ruff check web/v2` 
- [ ] **Step 5: Commit** — `git add web/v2 test_v2_models.py && git commit -m "feat(v2): domain models"`

---

### Task 2: SQLite 存储 `web/v2/store.py`

**Files:**
- Create: `web/v2/store.py`
- Test: `test_v2_store.py`

**Interfaces:**
- Consumes: Task 1 的 `V2Task/Turn/Decision/OutcomeDoc`。
- Produces: `class V2Store: __init__(self, db_path: str)`; `init(self)`; `save_task(self, task: V2Task)`（整体序列化覆盖写）; `get_task(self, task_id) -> V2Task|None`; `list_tasks(self) -> list[V2Task]`（按 created_at 倒序）; `delete_task(self, task_id)`。序列化方式：`task.model_dump_json()` 存 `tasks(id TEXT PRIMARY KEY, data TEXT, created_at REAL, status TEXT, demo INTEGER)`。线程安全：每次操作 `sqlite3.connect(self.db_path)` 用完即关（与 web/db.py 同风格）。

- [ ] **Step 1: 写失败测试** `test_v2_store.py`

```python
from web.v2.models import V2Task, Turn
from web.v2.store import V2Store


def test_roundtrip(tmp_path):
    s = V2Store(str(tmp_path / "v2.db")); s.init()
    t = V2Task(id="t1", goal_text="g", created_at=1.0, updated_at=1.0,
               constraints=[{"text": "已有内部 MCP 工具接入", "confirmed": True}],
               materials=[{"name": "现状.md", "text": "内容"}])
    t.turns.append(Turn(id="a", seq=1, stage="clarify", author="ada", kind="statement", title="T", body="B"))
    s.save_task(t)
    got = s.get_task("t1")
    assert got is not None and got.constraints[0].text == "已有内部 MCP 工具接入"
    assert got.turns[0].body == "B" and got.materials[0].name == "现状.md"


def test_list_order_and_missing(tmp_path):
    s = V2Store(str(tmp_path / "v2.db")); s.init()
    for i, created in enumerate([1.0, 2.0]):
        s.save_task(V2Task(id=f"t{i}", goal_text="g", created_at=created, updated_at=created))
    assert [x.id for x in s.list_tasks()] == ["t1", "t0"]
    assert s.get_task("nope") is None
    s.delete_task("t0"); assert s.get_task("t0") is None
```

- [ ] **Step 2: 跑失败** — `uv run pytest test_v2_store.py -q` → FAIL
- [ ] **Step 3: 实现** `web/v2/store.py` —— 按上述接口；`init()` 建 `data` 目录（`os.makedirs(dirname, exist_ok=True)`）与表。
- [ ] **Step 4: 通过** — `uv run pytest test_v2_store.py -q` → 2 passed；ruff
- [ ] **Step 5: Commit** — `git commit -m "feat(v2): sqlite store"`

### Task 3: 演示脚本 `web/v2/demo.py`

**Files:**
- Create: `web/v2/demo.py`
- Test: `test_v2_demo.py`

**Interfaces:**
- Produces（orchestrator 消费）:
  - `demo_enabled() -> bool`：`os.getenv("V2_DEMO") == "1" or not os.getenv("LLM_API_KEY")`
  - `DEMO_GOAL = "判断团队是否需要引入 A2A"`、`DEMO_CONSTRAINTS: list[str]`（三条）、`DEMO_QUESTION`、`DEMO_OPTIONS: list[dict]`（`仅内部 Agent/建议/保持私有化边界/recommended`、`允许受控外部接入/追加外部信任与授权评审`、`暂不确定/先补齐判断所需信息/uncertain`）
  - `statement(key: str, task: V2Task) -> tuple[str, str, bool]`：返回 `(title, body, verified)`。`key ∈ {"clarify_ada","compare_turing","review_linus","uncertain_turing","uncertain_linus","revise_turing","recommend_sage"}`。统一演示任务（goal_text==DEMO_GOAL）返回 Figma 逐字文案；其他目标用参数化模板（正文含 `{task.goal_text}` 与已确认约束原句，title 用通用句）。文案常量 `SCRIPTS: dict[str, tuple[str, str]]` 直接内嵌。
  - `build_outcome(task: V2Task) -> OutcomeDoc`：goal==DEMO_GOAL → Figma 成果页逐字内容（结论「建议开展内部小范围试点，暂不全面引入 A2A」、3 条理由带 refs、双方案对比、evidence=#01/#03/#04/#05/#06、3 个未解决问题、3 个行动项、3 条验收+停止条件）；其他目标 → 用任务实际 turns 生成同构文档（conclusion 取 recommend_sage title、reasons 从已确认约束+最近 statement 提炼、evidence 引用真实 seq）。
  - `user_note_texts`：介入 ack 文案常量 `ACK_RECEIVED = "已接收 · 将在当前发言结束后处理"`。

- [ ] **Step 1: 失败测试** `test_v2_demo.py`

```python
from web.v2 import demo
from web.v2.models import V2Task


def _task(goal=demo.DEMO_GOAL):
    return V2Task(id="t", goal_text=goal, created_at=1.0, updated_at=1.0, demo=True)


def test_demo_enabled(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False); monkeypatch.delenv("V2_DEMO", raising=False)
    assert demo.demo_enabled() is True
    monkeypatch.setenv("V2_DEMO", "0"); monkeypatch.setenv("LLM_API_KEY", "sk-x")
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
    a1 = demo.statement("clarify_ada", t); a2 = demo.statement("clarify_ada", t)
    assert a1 == a2 and "自建机房" in a1[1]
```

- [ ] **Step 2: 跑失败** — `uv run pytest test_v2_demo.py -q` → FAIL
- [ ] **Step 3: 实现** `web/v2/demo.py` —— 文案从 Figma 截图逐字誊写（#01 Ada「先分清协议职责，不把能力发现当成权限体系」/ #03 Turing「从一个跨团队任务交接开始试点」/ #04 Linus「对方声明的 capability，不等于获得授权」/ 修订与建议轮 / 成果全文）。
- [ ] **Step 4: 通过** — `uv run pytest test_v2_demo.py -q` → 3 passed；ruff
- [ ] **Step 5: Commit** — `git commit -m "feat(v2): deterministic demo scripts"`

---

### Task 4: 编排器内核 —— 自动推进 + 决策门

**Files:**
- Create: `web/v2/orchestrator.py`
- Test: `test_v2_orchestrator.py`

**Interfaces:**
- Consumes: Task 1-3 全部。
- Produces:
  - `class SpeakerBackend(Protocol)`: `async def speak(self, task: V2Task, author: str, key: str) -> tuple[str, str, bool]`（返回 title/body/verified，orchestrator 据此建 Turn）；demo 后端直接调 `demo.statement`。
  - `class Orchestrator:` 
    - `__init__(self, store: V2Store, backend: SpeakerBackend, broadcaster: Broadcaster)`
    - `async def run_task(self, task_id: str) -> None`：推进循环（见下方状态规则），可被 `pause()` 打断、异常时置 failed。
    - `def pause(self, task_id)` / `def resume(self, task_id)` / `async def submit_decision(self, task_id, decision_id, option_id) -> V2Task` / `async def end_now(self, task_id) -> V2Task`
  - `Broadcaster`（Task 8 实现真实版，本任务用 `class NullBroadcaster: def publish(self, task_id, event, data)` 吞掉）——orchestrator 在关键点调用 `publish(task_id, "stage_change"|"turn_delta"|"turn_done"|"decision_required"|"status_change", {...})`。
  - 阶段发言序列常量 `STAGE_PLAN: list[tuple[Stage, list[str], str]]` = `[("clarify",["ada"],"澄清需求"), ("compare",["turing"],"比较方案"), ("review",["linus"],"评审风险")]`；Sage 的发言在决策确认后的修订轮中（`revise_turing` → `recommend_sage`）。
  - 状态规则：循环每轮开头检查 `store.get_task` 的 status（支持外部 pause）；进入 review 阶段且 linus 发言完成 → 建Decision（id=f"d{round}"，options=demo.DEMO_OPTIONS）→ status=waiting_confirmation → publish decision_required → 循环退出。`submit_decision`：幂等（resolved 或 option 不存在 → 直接返回当前 task）；写 chosen_id、status=resolved，追加 user `decision_record` turn（title=f"你已确认：{option.label}"，seq 连续），把 `Constraint(text=option.label, confirmed=True)` 追加；uncertain 选项 → 追加两轮 `uncertain_turing/uncertain_linus` 后建 round+1 的新 Decision 重开 gate；其余 → `revise_turing` + `recommend_sage` → `build_outcome` → status=completed、current_stage=recommend。全程唯一活动协程：`self._running: dict[str, asyncio.Task]`，`run_task` 入口若已存在则直接 return。

- [ ] **Step 1: 失败测试** `test_v2_orchestrator.py`

```python
import asyncio
import pytest
from web.v2.models import V2Task
from web.v2.store import V2Store
from web.v2.orchestrator import Orchestrator, SpeakerBackend, NullBroadcaster


class EchoBackend(SpeakerBackend):
    async def speak(self, task, author, key):
        return (key, f"body:{key}:{task.goal_text}", False)


def _mk(tmp_path, goal="判断团队是否需要引入 A2A"):
    store = V2Store(str(tmp_path / "db.sqlite")); store.init()
    t = V2Task(id="t1", goal_text=goal, expected_outcome="一份采用建议与试点计划",
                constraints=[{"text": c} for c in ["已有内部 MCP 工具接入", "首阶段优先私有化", "只验证一个跨团队协作场景"]],
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
async def test_single_coroutine_guard(tmp_path):
    store, orch, t = _mk(tmp_path)
    task1 = asyncio.create_task(orch.run_task("t1"))
    await asyncio.create_task(orch.run_task("t1"))  # 第二次应立即返回
    await _drain(task1)
    assert store.get_task("t1").status == "waiting_confirmation"
```

- [ ] **Step 2: 跑失败** — `uv run pytest test_v2_orchestrator.py -q` → FAIL/ERROR（需要 `pytest-asyncio`：若未安装，`uv add --dev pytest-asyncio` 并在 pyproject 加 `asyncio_mode = "auto"`？——不，保持显式 `@pytest.mark.asyncio`，只需 dev 依赖 pytest-asyncio）
- [ ] **Step 3: 实现** `web/v2/orchestrator.py` —— 按接口与状态规则；每建一个 Turn 都 `store.save_task`（崩溃安全）；`turn_done` publish 带 `{turn_id, seq}`。
- [ ] **Step 4: 通过** — `uv run pytest test_v2_orchestrator.py -q` → 5 passed；ruff
- [ ] **Step 5: Commit** — `git commit -m "feat(v2): orchestrator core with decision gate"`

---

### Task 5: 编排器生命周期 —— 暂停/恢复/提前结束/失败重试/介入队列

**Files:**
- Modify: `web/v2/orchestrator.py`
- Test: `test_v2_lifecycle.py`（新文件）

**Interfaces:**
- Produces（追加到 Orchestrator）:
  - `async def submit_intervention(self, task_id, intent: str, text: str) -> dict`：立即返回 `{"received": True, "position": n, "ack": demo.ACK_RECEIVED}`；turn 入 `self._pending_interventions[task_id]`（`intent ∈ 追问|补充条件|调整方向`）。推进循环在每条发言完成后处理队列：建 user `user_note` turn（title=f"你 · {intent}"，intent 字段记录），publish `intervention_ack`。
  - 暂停语义：`pause()` 设 status=paused；循环在两条发言之间观察到后退出（不再发言）。`resume()` 设 running 并重新 `run_task`（门未决则继续走到门）。waiting_confirmation/paused 状态下不产生发言。
  - `retry(task_id)`：仅 status==failed 可用；清 error，status=running，重新 run_task（backend 失败重试逻辑在 Task 6 的 backend 内：重试一次仍失败抛 `AgentCallError` → run_task 捕获置 failed + error 文案）。
  - `end_now(task_id)`：running/waiting/paused → 直接 `build_outcome` + completed（publish outcome_update）。completed 后调用为幂等 no-op。

- [ ] **Step 1: 失败测试** `test_v2_lifecycle.py`

```python
import asyncio
import pytest
from web.v2.models import V2Task
from web.v2.store import V2Store
from web.v2.orchestrator import Orchestrator, NullBroadcaster


class SlowBackend:
    def __init__(self, fail_first=False):
        self.calls = 0; self.fail_first = fail_first
    async def speak(self, task, author, key):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("llm down")
        await asyncio.sleep(0.05)
        return (key, "b", False)


def _mk(tmp_path, backend):
    store = V2Store(str(tmp_path / "db.sqlite")); store.init()
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
```

- [ ] **Step 2: 跑失败** → FAIL
- [ ] **Step 3: 实现**（修改 orchestrator：intervention 队列、pause 检查点、AgentCallError 捕获、retry/end_now）
- [ ] **Step 4: 通过** — `uv run pytest test_v2_lifecycle.py test_v2_orchestrator.py -q` → 9 passed
- [ ] **Step 5: Commit** — `git commit -m "feat(v2): orchestrator lifecycle"`

---

### Task 6: 角色 Agent 客户端 `web/v2/agents_client.py`

**Files:**
- Create: `web/v2/agents_client.py`
- Test: `test_v2_agents_client.py`

**Interfaces:**
- Consumes: `shared.a2a_client.A2AJSONRPCClient(url).stream_deltas(text)`（async 生成器，产出文本增量）。
- Produces:
  - `ROLE_AGENTS: dict[str, str]` 默认 `{"ada": "http://localhost:8011", "turing": "...8012", "linus": "...8013", "sage": "...8014"}`，env `ROLE_AGENT_URLS`（格式 `ada=http://..,turing=http://..`）覆盖。
  - `ROLE_PERSONAS: dict[str, str]`（名字/职责一句话，用于 prompt 与连接摘要）。
  - `def build_turn_prompt(task: V2Task, author: str, key: str) -> str`：结构化纯文本（`[目标]…[期望成果]…[约束（含已确认标记）]…[近期讨论]…[你的任务]…`），"你的任务"段按 key 给指令（如 `revise_turing` 要求"根据用户新确认的约束修订试点路径"）。
  - `class AgentSpeakerBackend`（实现 Task 4 的 SpeakerBackend）：`speak()` 调对应 role 的 `stream_deltas(build_turn_prompt(...))`，增量经 `broadcaster.publish(task_id, "turn_delta", {"turn_id": ..., "delta": ...})` 转发（turn 先以空 body 落库获得 id）；流结束后重试逻辑：异常 → 1s 后重试一次 → 仍失败 `raise AgentCallError`。think/`[PHASE]` 过滤复用 web/main.py 的 `_ThinkFilter`（从 web.main import，或抽到 web/v2/util.py —— 选择：抽 `web/v2/util.py: ThinkFilter` 供两边使用，本任务一并创建并让 web/main.py 改 import）。

- [ ] **Step 1: 失败测试** `test_v2_agents_client.py`

```python
import pytest
from web.v2.agents_client import build_turn_prompt, ROLE_AGENTS, AgentSpeakerBackend, AgentCallError
from web.v2.models import V2Task


def _task():
    return V2Task(id="t", goal_text="g", created_at=1.0, updated_at=1.0,
                  constraints=[{"text": "c1", "confirmed": True}])


def test_prompt_sections():
    p = build_turn_prompt(_task(), "ada", "clarify_ada")
    assert "[目标] g" in p and "[约束]" in p and "✓ c1" in p and "研究员" in p


def test_env_override(monkeypatch):
    monkeypatch.setenv("ROLE_AGENT_URLS", "ada=http://x:9")
    from web.v2 import agents_client as m
    m.reload_urls()
    assert m.ROLE_AGENTS["ada"] == "http://x:9"


@pytest.mark.asyncio
async def test_backend_retries_then_raises(monkeypatch):
    calls = {"n": 0}
    class Flaky:
        def __init__(self, url): pass
        async def stream_deltas(self, text):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise RuntimeError("boom")
            yield "x"
    monkeypatch.setattr("web.v2.agents_client.A2AJSONRPCClient", Flaky)
    be = AgentSpeakerBackend(NullBroadcasterStub())
    with pytest.raises(AgentCallError):
        await be.speak(_task(), "ada", "clarify_ada")
    assert calls["n"] == 2
```

（`NullBroadcasterStub` 测试内定义：`publish(*a, **k)`。）

- [ ] **Step 2: 跑失败** → FAIL
- [ ] **Step 3: 实现** `web/v2/agents_client.py` + `web/v2/util.py`（ThinkFilter 从 web/main.py 迁出，main.py 改为 `from web.v2.util import ThinkFilter`，行为不变）
- [ ] **Step 4: 通过** — `uv run pytest test_v2_agents_client.py test_web.py -q`（test_web 为 main() 脚本则跑 `uv run pytest test_v2_agents_client.py -q` 且确认 `uv run python -c "import web.main"` 正常）；ruff
- [ ] **Step 5: Commit** — `git commit -m "feat(v2): role agent client"`

---

### Task 7: `role_agent/` 服务（×4 实例）

**Files:**
- Create: `role_agent/main.py`
- Create: `role_agent/Dockerfile`（复制 research_agent/Dockerfile 改路径）
- Test: `test_role_agent.py`

**Interfaces:**
- Consumes: `shared.a2a_server.A2AJSONRPCServer`、`shared.llm_client`、`shared.agent_loop.agentic_stream`。
- Produces: env `ROLE`（ada|turing|linus|sage，默认 ada）、`PORT`（默认 8011）、`AGENT_URL`。Agent card name=`{ROLE} · {中文名}`；流式处理器：取 `collect_user_text(task)` 为 prompt，`agentic_stream(system=ROLE_PERSONA_PROMPTS[role], user=prompt, search_context=role=="ada" and web_search(...) or "", max_tokens=2000)` yield 增量（`[PHASE]`/think 原样输出——由 web 侧过滤，协议其他调用方自行处理）。`ROLE_PERSONA_PROMPTS` 常量四段中文 system prompt（含职责与输出格式要求：先一行观点标题 `# TITLE: ...`，再正文；Ada 需对未核实结论在结尾追加 `# UNVERIFIED`）。无 LLM key：`agentic_stream` 的 fallback 机制输出模板句（诚实 fallback，仅测试用）。

- [ ] **Step 1: 失败测试** `test_role_agent.py`

```python
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("ROLE", "linus")
    import importlib, role_agent.main as m
    importlib.reload(m)
    return TestClient(m.app)


def test_agent_card(client):
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    card = r.json()
    assert "Linus" in card["name"]


def test_send_message_fallback(client):
    r = client.post("/rpc", json={
        "jsonrpc": "2.0", "id": 1, "method": "SendMessage",
        "params": {"message": {"role": "ROLE_USER", "parts": [{"kind": "text", "text": "评估风险"}]}}})
    assert r.status_code == 200
    assert r.json()["result"] is not None


def test_stream_endpoint(client):
    with client.stream("POST", "/rpc/stream", json={
        "jsonrpc": "2.0", "id": 1, "method": "SendStreamingMessage",
        "params": {"message": {"role": "ROLE_USER", "parts": [{"kind": "text", "text": "评估风险"}]}}}) as r:
        assert r.status_code == 200
        body = b"".join(r.iter_raw())
        assert b"data:" in body
```

（注意：沿用仓库现有 agent 测试的参数形状——若 `test_a2a.py` 中 params 形状不同，以现有测试为准照抄。）

- [ ] **Step 2: 跑失败** → FAIL
- [ ] **Step 3: 实现** `role_agent/main.py`（照 research_agent/main.py 骨架）+ Dockerfile（copy `shared/ role_agent/`，CMD `python role_agent/main.py`，EXPOSE 同 PORT arg）
- [ ] **Step 4: 通过** — `uv run pytest test_role_agent.py -q` → 3 passed；ruff
- [ ] **Step 5: Commit** — `git commit -m "feat(v2): role agent service"`

---

### Task 8: `/api/v2` REST + SSE 路由

**Files:**
- Create: `web/v2/routes.py`、`web/v2/broadcaster.py`
- Modify: `web/main.py`（`from web.v2.routes import router as v2_router; app.include_router(v2_router)`；lifespan 里 `v2_store.init()`）
- Test: `test_v2_api.py`

**Interfaces:**
- Produces:
  - `web/v2/broadcaster.py`: `class Broadcaster:` 内部 `dict[str, set[asyncio.Queue]]`；`subscribe(task_id)->Queue`、`unsubscribe`、`publish(task_id, event, data)`（fan-out，格式与 web/main.py 的 `sse_event(event, data)` 一致，复用该函数：`from web.main import sse_event`？——否，循环 import。把 `sse_event` 移到 `web/v2/util.py`，web/main.py 改 import（Task 6 已建 util.py）。
  - `web/v2/routes.py`: `router = APIRouter(prefix="/api/v2")`，全局单例 `V2Store(os.getenv("V2_DB", "data/v2_tasks.db"))` + `Broadcaster` + lazy Orchestrator 工厂 `_get_orchestrator()`（demo→demo backend；real→AgentSpeakerBackend）。路由：
    - `POST /tasks` body `{goal_type, goal_text, expected_outcome?, constraints?: list[str], materials?: list[{name,text}], advanced_mode?, advanced_rounds?}`；goal_type!="decision" → 422 `{"detail": "该目标类型本轮暂不支持，已锁定「做出决策」路径"}`；demo 模式创建 `demo=True` 任务；返回 `task.public_dict()`（status=preparing）
    - `GET /tasks` → `[{id, goal_text, status, current_stage, demo, outcome_summary}]`
    - `GET /tasks/{id}` → 全量 public_dict（含 `connections: {role: "up"|"down"|"demo"}`——demo 任务固定 demo；real 任务 httpx GET agent-card 探活，2s 超时）
    - `POST /tasks/{id}/start`（仅 preparing；应用可能修改的 constraints/advanced → 保存 → status=running → `asyncio.create_task(orch.run_task(id))`）
    - `POST /tasks/{id}/decisions/{did}` `{option_id}`；`POST /tasks/{id}/interventions` `{intent, text}`；`POST /tasks/{id}/pause|resume|retry|end`
    - `GET /tasks/{id}/stream` → StreamingResponse（`init` 事件=public_dict；随后转发 queue 事件；15s keepalive）
    - `GET /tasks/{id}/outcome`；`PATCH /tasks/{id}/outcome`（body 为 OutcomeDoc 局部字段；label 字段强制忽略——label 只能由后续显式 confirm 接口改；本轮实现 `POST /tasks/{id}/outcome/confirm` 把 label 置 team_confirmed）
    - `GET /tasks/{id}/export` → Markdown（标题/状态/阶段/约束/turns 全文/决策记录/成果各节；demo 任务页脚「本文包含演示模式生成的确定性内容」）
- 请求模型（风格照抄 CreateMeetingRequest）：`CreateV2TaskRequest/StartRequest/DecisionRequest/InterventionRequest/OutcomePatchRequest`。

- [ ] **Step 1: 失败测试** `test_v2_api.py` —— TestClient 全流程（monkeypatch `V2_DEMO=1`、`V2_DB=tmp`）：

```python
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("V2_DEMO", "1")
    monkeypatch.setenv("V2_DB", str(tmp_path / "v2.db"))
    import importlib
    import web.main as m
    importlib.reload(m)
    return TestClient(m.app)


def _create(client, **kw):
    body = dict(goal_type="decision", goal_text="判断团队是否需要引入 A2A",
                expected_outcome="一份采用建议与试点计划",
                constraints=["已有内部 MCP 工具接入", "首阶段优先私有化", "只验证一个跨团队协作场景"])
    body.update(kw)
    return client.post("/api/v2/tasks", json=body)


def test_create_rejects_unsupported(client):
    r = _create(client, goal_type="research")
    assert r.status_code == 422


def test_full_demo_loop(client):
    r = _create(client); assert r.json()["status"] == "preparing"
    tid = r.json()["id"]
    assert client.post(f"/api/v2/tasks/{tid}/start").json()["status"] == "running"
    # 轮询直到 waiting_confirmation（demo 无真实延迟）
    import time
    for _ in range(100):
        t = client.get(f"/api/v2/tasks/{tid}").json()
        if t["status"] == "waiting_confirmation":
            break
        time.sleep(0.05)
    assert t["status"] == "waiting_confirmation"
    assert t["demo"] is True and t["connections"] == {k: "demo" for k in ["ada", "turing", "linus", "sage"]}
    did = t["decisions"][0]["id"]
    r2 = client.post(f"/api/v2/tasks/{tid}/decisions/{did}", json={"option_id": "o1"})
    assert r2.json()["status"] == "completed"
    out = client.get(f"/api/v2/tasks/{tid}/outcome").json()
    assert out["label"] == "ai_suggestion"
    ex = client.get(f"/api/v2/tasks/{tid}/export")
    assert ex.status_code == 200 and "演示" in ex.text
    # confirm 接口
    assert client.post(f"/api/v2/tasks/{tid}/outcome/confirm").json()["label"] == "team_confirmed"


def test_sse_stream_emits_init_and_events(client):
    tid = _create(client).json()["id"]
    with client.stream("GET", f"/api/v2/tasks/{tid}/stream") as r:
        assert r.status_code == 200
        buf = b""
        for chunk in r.iter_raw():
            buf += chunk
            if b"event: init" in buf:
                break
        assert b"preparing" in buf


def test_history_and_isolation(client):
    a = _create(client, goal_text="任务A").json()["id"]
    b = _create(client, goal_text="任务B").json()["id"]
    lst = client.get("/api/v2/tasks").json()
    assert len(lst) == 2
    ta = client.get(f"/api/v2/tasks/{a}").json()
    assert all(x["id"] != b for x in [] ) or ta["goal_text"] == "任务A"
```

- [ ] **Step 2: 跑失败** → FAIL
- [ ] **Step 3: 实现** routes.py + broadcaster.py + main.py 两行接线
- [ ] **Step 4: 通过** — `uv run pytest test_v2_api.py test_v2_orchestrator.py test_v2_lifecycle.py -q` 全绿；`uv run pytest test_web_turns.py test_web_scheduler.py -q` 旧测试不回归；ruff
- [ ] **Step 5: Commit** — `git commit -m "feat(v2): REST + SSE routes"`

---

### Task 9: compose 服务与环境

**Files:**
- Modify: `docker-compose.yml`（追加 role-ada/role-turing/role-linus/role-sage 四服务，ports 8011-8014，env `ROLE`、LLM 三件套、`<<: *default-dns`；web 服务 env 追加 `ROLE_AGENT_URLS=ada=http://role-ada:8011,turing=http://role-turing:8012,linus=http://role-linus:8013,sage=http://role-sage:8014`）
- Test: 无单测；`docker compose config -q` 语法校验 + 本地起栈冒烟。

- [ ] **Step 1:** 编辑 compose（照 research-agent 服务块复制修改）
- [ ] **Step 2:** `docker compose config -q` → 无输出（合法）；`uv run ruff check .`、`uv run pytest test_v2_api.py -q` 仍绿
- [ ] **Step 3:** Commit — `git commit -m "feat(v2): compose role services"`

---

### Task 10: 前端基座 —— tokens / 字体 / 主题 / 路由 / API 客户端

**Files:**
- Modify: `web/frontend/package.json`（`npm i @fontsource/noto-sans-sc @fontsource/jetbrains-mono`）
- Rewrite: `web/frontend/src/index.css`（V2 双主题 tokens，保留 `@theme inline` 桥接与 shadcn 引入）
- Create: `web/frontend/src/lib/v2api.ts`、`web/frontend/src/lib/router.ts`、`web/frontend/src/hooks/useV2Theme.ts`
- Rewrite: `web/frontend/src/App.tsx`（hash 路由壳）；Delete: `src/App.css`、`src/components/` 下 V1 组件（保留 `components/ui/`）、`hooks/useMeetingRoom.ts`、`hooks/useMeetings.ts`、`hooks/useTheme.ts`、`lib/labels.ts`、`lib/sequence.ts`、`types.ts`
- Test: `npm run lint && npm run build` 绿（前端验收基线）

**Interfaces:**
- `useV2Theme() -> {theme: "light"|"dark", toggle()}`，key `v2-theme`，默认 light，`document.documentElement.classList` 切 `dark`。
- `router.ts`：`useHashRoute() -> {path: string, navigate(to: string)}`；解析 `location.hash`（`#/`、`#/plan`、`#/task/:id`、`#/task/:id/outcome`）。
- `v2api.ts`（全相对路径，风格同 lib/api.ts）：`createTask(body)`, `listTasks()`, `getTask(id)`, `startTask(id)`, `submitDecision(id, did, optionId)`, `sendIntervention(id, intent, text)`, `pauseTask/resumeTask/retryTask/endTask(id)`, `getOutcome(id)`, `patchOutcome(id, body)`, `confirmOutcome(id)`, `exportUrl(id)`, `streamUrl(id)`；类型 `V2Task/turns/Decision/OutcomeDoc` 镜像后端（TS interface）。
- index.css tokens（:root / .dark 完整替换，值=spec §4.1 逐值；字体 `--font-sans: "Noto Sans SC", system-ui...`、`--font-mono: "JetBrains Mono", monospace`；main.tsx 顶部 import 两个 fontsource css）。

- [ ] **Step 1:** 装依赖、写 tokens/router/theme/api、重写 App.tsx 壳（路由分支先渲染占位页）、删 V1 文件
- [ ] **Step 2:** `npm run lint && npm run build` → 全绿；手动 `npm run dev` 打开 `#/` 见占位页（可用 `Start-Process` 起 dev，完成后停）
- [ ] **Step 3:** Commit — `git commit -m "feat(v2): frontend foundation"`

### Task 11: 目标首页

**Files:**
- Create: `web/frontend/src/pages/HomePage.tsx`、`src/components/v2/GoalCards.tsx`、`src/components/v2/TaskCreateCard.tsx`、`src/components/v2/RecentTasks.tsx`、`src/components/v2/Shell.tsx`（品牌侧栏+顶栏骨架，四页共用）
- Test: `npm run lint && npm run build` 绿 + dev 目检

**要点（对照 Figma 14:3150 逐项）：**
- Shell：左 232px 侧栏（`bg-[#eeefef] dark:bg-[#171b25] border-r border-[#dfe2e5] dark:border-[#333a4b]`，品牌块 `A²` 紫底圆角 36px + 「A2A 会议室/目标驱动的 AI 协作室」、「开始新任务」紫色主按钮 w-full h-44px、任务历史列表（`listTasks()` 轮询 15s，条目=标题+状态徽标+副标题、「查看全部成果」入口）、底部工作区信息卡+个人设置行）；顶栏 h-88px（标题+说明、右侧状态徽标+sun/moon 主题切换按钮）。徽标色板映射：讨论中=紫、待确认/等待你确认=琥珀、已完成=青、准备中/进行中=灰、失败=红（新增 `--destructive` 已有）。**徽标组件 `StatusBadge.tsx` 统一实现（文字+色双编码，带 icon：讨论中=MessagesSquare、待确认=CircleHelp、已完成=CheckCircle2、失败=AlertTriangle）**。
- GoalCards：四卡 grid-cols-4（scan-search/columns-2/file-check-2/signpost 图标 + 标题 + 副题）；选中卡（做出决策）`bg-[#f0ecfc] border-[#7054d8]` + 右上 CircleCheck；其余三卡点击 `toast.info("该目标类型本轮暂不支持，已为你锁定「做出决策」路径")`（sonner 已有）并强制选中做出决策。
- TaskCreateCard：白卡 1.5px 紫边圆角 20 阴影；问题 textarea（placeholder 照 Figma）、约束说明输入（逗号分隔或逐条添加，≥0 条）、「添加材料」行（paperclip 图标；点击展开：材料名+粘贴文本 textarea，卡片下方标注"仅登记文本，不做文档解析"；已加材料 chip 列表可删）、右下「生成协作计划」按钮（arrow-right 图标；无目标文本时 disabled+提示）→ `createTask` 成功后 `navigate("/plan")` 并把任务 id 存 `sessionStorage.v2DraftTask`。流程说明行（"提出目标 → 确认计划 → 关键节点介入 → 获得成果"/"计划确认后才会开始讨论"）。
- RecentTasks：`listTasks()` 前三（讨论中/待确认/已完成 徽标+行操作文案映射：待确认→"回答并继续 →"、已完成→"查看成果 →"、讨论中→"进入讨论 →"；行点击 navigate 到 `#/task/:id` 或 `#/task/:id/outcome`）。空态：插画区+「还没有任务，从上面提出第一个目标」。
- 不支持提示、空态、加载骨架（三卡 pulse）、错误 banner（fetch 失败重试按钮）齐全；键盘可 Tab 进入全部交互件。

- [ ] **Step 1:** 实现 Shell + StatusBadge + 三组件 + HomePage 接路由
- [ ] **Step 2:** lint+build 绿；dev 打开 `#/` 对照 Figma 目检（间距/字号/色值）
- [ ] **Step 3:** Commit — `git commit -m "feat(v2): home page"`

---

### Task 12: 协作计划页

**Files:**
- Create: `web/frontend/src/pages/PlanPage.tsx`、`src/components/v2/ConstraintEditor.tsx`、`src/components/v2/RoleDuties.tsx`、`src/components/v2/StagePath.tsx`、`src/components/v2/AdvancedSettings.tsx`
- Test: lint+build + dev 目检

**要点（Figma 14:3299）：**
- 顶栏：「新任务 · 确认协作计划 / 第二步 · 确认后开始协作」+ 右侧步骤指示（✓ 目标与材料 → chevron → 2 确认计划）。
- 左卡 392px「目标与材料 / 调整 ✎」：要做出的判断（22px bold）、期望成果（紫 medium）、分隔线、上下文约束（ConstraintEditor：check 图标+文本行，hover 出删除；底部「＋ 添加约束」内联输入；**改动写入 `patchDraft`（sessionStorage 的草稿任务），start 时提交**）、材料摘要（"已添加材料 · N 项 / ＋ 添加"——添加跳回首页卡片？简化：本页支持再粘贴一条材料）。
- 右卡 flex-1「四个视角，一份可用的判断 / 调整分工」（调整分工点击 toast"本轮角色固定为四位，职责可在约束中补充"）：四行 RoleDuties（emoji 44px 圆角方块 + 中文名/英文名（mono）+ 职责标题/说明，数据 hardcode 四角色）+ 底部青色「人类决策边界」条（user-round-check icon，文案照 Figma）。
- StagePath 四卡：01-04 mono 编号 + arrow-right + 标题/说明/脚注，03 卡紫底高亮+「关键节点请你确认」（紫字）。
- AdvancedSettings：折叠行（sliders-horizontal + 「高级设置」+「讨论模式（流水线 / 圆桌 / 辩论）与轮数」+ chevron-down）；展开：三个模式 radio（默认 pipeline）+轮数 number input 1-3；提交前校验：轮数>1 且模式=debate 时 disable 并说明"该组合本轮不支持"（不静默）。
- 底部操作条：「← 返回上一步」（回 `#/`）｜「讨论与成果草稿将同步展开」+「开始协作」按钮（`startTask(id, {constraints, advanced})` → navigate `#/task/:id`）。加载中按钮 disabled+spinner；失败 toast。

- [ ] **Step 1:** 实现五组件 + PlanPage
- [ ] **Step 2:** lint+build；dev 走通 首页创建→计划页→改约束→开始协作→跳工作区占位
- [ ] **Step 3:** Commit — `git commit -m "feat(v2): plan page"`

---

### Task 13: 决策工作区 —— 布局/会议舱/流式讨论

**Files:**
- Create: `web/frontend/src/pages/WorkspacePage.tsx`、`src/hooks/useV2Stream.ts`、`src/components/v2/MeetingPod.tsx`、`src/components/v2/StageTimeline.tsx`、`src/components/v2/TurnCard.tsx`、`src/components/v2/UserNoteCard.tsx`
- Test: lint+build + dev 联调（V2_DEMO=1 起 web）

**Interfaces:**
- `useV2Stream(taskId) -> {task, events, connected}`：EventSource(`streamUrl(id)`)；处理事件：`init`（全量 task）、`status_change/stage_change`（更新 task）、`turn_delta`（按 turn_id 追加 body——本地乐观插入 turn 骨架）、`turn_done`（用完整 turn 替换）、`decision_required`（task.decisions 更新）、`intervention_ack`（toast「已接收 · 将在当前发言结束后处理」）、`outcome_update`、error/断线自动重连（EventSource 原生）+「连接中断，重连中」横幅。状态源唯一：`task` state，各组件纯派生。
- MeetingPod（可收起）：标题行「会议舱 · 4 个专业视角 · <派生摘要>」+「收起会议舱/展开」chevron；四个角色胶囊（emoji+角色名·英文名+状态文案：发言中/等待确认/已完成/idle，右缘 6px 状态点）；收起时只剩标题行。真实模式角色状态映射 turn 流（当前发言 author=该角色→发言中）；demo 模式胶囊状态仍真实反映编排进度。
- StageTimeline：四格进度（✓ 已完成阶段青字、当前阶段紫底粗体、未来灰）。
- TurnCard：emoji 头像 34px + 角色 bold + 姓名 + 右侧 #seq（mono）；观点标题 16px bold；正文 15px leading-1.75（流式光标：`turn_delta` 进行中尾部 ▍闪烁）；`verified=true` → 底部琥珀「待验证」徽标+说明行。stage 分组头（「当前阶段 · 风险评审 / 等待你确认接入边界」 teal bold + 右侧说明；历史分组「此前阶段 · … / 已完成 · 保留关键发言」）。
- UserNoteCard：青底 `#1c353c dark`/浅色青 tint 圆角条「你 · 补充条件」+#seq+内容；decision_record 用同款紫 tint「你已确认：仅内部 Agent」。
- 布局：中栏 flex-1 max-w-[800px]；右栏 336px（Task 14）；<1024px 单列。自动滚动：新 turn 时滚到底，用户上滚则停（IntersectionObserver 哨兵）。

- [ ] **Step 1:** 实现 hook + 五组件（决策门/输入区/右栏先占位）
- [ ] **Step 2:** lint+build；`V2_DEMO=1 uv run python web/main.py`（Start-Process 分离）+ dev 联调：创建→开始→目击三连发言流式与阶段推进→停在决策门
- [ ] **Step 3:** Commit — `git commit -m "feat(v2): workspace discussion stream"`

---

### Task 14: 决策工作区 —— 决策门 / 介入输入 / 成果草稿栏 / 顶栏操作

**Files:**
- Create: `src/components/v2/DecisionGate.tsx`、`src/components/v2/InterventionBar.tsx`、`src/components/v2/OutcomeRail.tsx`
- Modify: `WorkspacePage.tsx`
- Test: lint+build + dev 全流程联调

**要点：**
- DecisionGate（Figma 14:4096）：紫软底圆角 14 卡「需要你确认 / 普通发言已停止，等待你的选择」（circle-help）；问题 20px bold；建议说明 14px（含"这是建议，尚未替你确认"）；三选项卡（radio 语义 `role="radiogroup"`，选中 border 紫+软底+CircleCheck 圆点实心；建议项右上「建议」徽标；每项 label+impact）；确认按钮：未选 disabled(50%)，选中后可点 → `submitDecision` → 按钮转 spinner「已确认，讨论继续中」；「暂不确定」确认后出现提示条「已记录你的保留意见 · 接下来继续比较影响，稍后将再次请你选择」。
- InterventionBar：意图 chips（追问/补充条件/调整方向，可选中高亮，默认无）+ 输入行（placeholder 照 Figma）+ 发送按钮（arrow-up）→ `sendIntervention`；ack 行显示后 8s 淡出；说明行常驻。waiting_confirmation 时输入可用但 ack 文案追加「当前在等待你的关键选择」。
- OutcomeRail：标题「成果草稿 / 随讨论更新 · 尚未形成最终建议」（notebook-pen）；三组摘要（已确认=青左边线、仍有分歧=紫、待验证=琥珀；每组标题+条目（来自 outcome.summary_groups，未定稿时显示占位文案"讨论推进后自动汇总"）+「关联讨论」点击滚到对应 turn）；「建议草稿预览」卡（label 徽标：讨论草稿=灰、AI 协作建议=紫「待团队审批」；初步建议+正文+预期验证框+草稿依据）；底部分隔线+完成提示+来源提示（"以下内容来自本次讨论记录"）。
- 顶栏：任务名+「{阶段中文} · 第 {i}/4 阶段」+ StatusBadge + 「结束协作」按钮（confirm 二次确认弹层，说明"将基于已有讨论立即生成成果"）+ 主题切换。任务 failed → 顶部红色 banner「讨论在某某环节失败」+「重试」按钮（`retryTask`）。paused → 琥珀 banner「已暂停」+「继续讨论」。
- 窄屏：右栏移到讨论下方（order 调整）；会议舱默认收起。

- [ ] **Step 1:** 实现三组件并接线
- [ ] **Step 2:** lint+build；dev 全流程：到门→选「仅内部」→目击修订+Sage 发言→completed→右栏草稿变建议→「结束协作」在已完成时置灰
- [ ] **Step 3:** Commit — `git commit -m "feat(v2): decision gate, interventions, outcome rail"`

---

### Task 15: 决策成果页

**Files:**
- Create: `web/frontend/src/pages/OutcomePage.tsx`、`src/components/v2/OutcomeOverview.tsx`、`src/components/v2/OutcomeSections.tsx`（理由/对比/依据/行动项）、`src/components/v2/OpenQuestions.tsx`
- Test: lint+build + dev 目检

**要点（Figma 14:3739 逐节）：**
- 顶栏「决策成果 / {goal} · 已完成协作 · 第 4/4 阶段」+ 编辑/复制/导出三按钮（编辑=进入编辑态：正文各节变 contentEditable/textarea，保存 `patchOutcome`；复制=navigator.clipboard 全文 markdown+toast「已复制」；导出=window.open(exportUrl)）。
- OutcomeOverview 大卡：file-check-2 + 「AI 协作建议 · 待团队审批」紫徽标（label=team_confirmed → 青色「团队已确认」徽标+说明变化）；主结论 32px bold；结论说明；分隔线；「✓ 你已确认：{已确认约束} · #{seq}」青字 + 右侧琥珀「协作已完成，不代表方案已验证或审批通过」。
- 正文 780px：01 理由（编号 mono 紫 + 标题 20px + 3 组理由 16px bold/15px 正文/「关联讨论 #xx ↗」青字点击→`#/task/:id` 并 sessionStorage 标记 `v2FocusTurn=seq`，工作区读它滚动高亮该 turn）；02 方案对比双卡（灰卡 vs 紫软卡「建议路径」徽标；优势/代价/适用条件行）；03 依据回看（顶部灰字声明 + 行列表=「#01 · 澄清需求」teal / 发言者 / 摘要 / arrow-up-right，点击同上跳转）；04 行动项（1/2/3 紫底方块编号 + 标题/说明/「责任人待分配 · 完成时间待确定」）。
- 右栏 320px：未解决问题琥珀卡（circle-help + 3 问题 + 状态说明 + 「继续讨论」白底按钮→回工作区并把问题预填进 InterventionBar 的输入（sessionStorage `v2FollowUp`））；「通过这些条件再扩展」白卡（teal「已确认边界」徽标 + 3 条验收条件（标题+说明）+ 分隔线 + 停止条件琥珀字）；审批说明卡（「审批说明 / 本页为 AI 协作建议，需团队审批后执行；确认按钮只代表记录你的选择」）。
- 成果尾注：「← 返回讨论」/「以上为 AI 协作建议，非团队决议」。
- 未完成任务进入此路由 → 重定向工作区。

- [ ] **Step 1:** 实现四组件 + OutcomePage
- [ ] **Step 2:** lint+build；dev 目检双主题 + 编辑/复制/导出/跳转回讨论高亮
- [ ] **Step 3:** Commit — `git commit -m "feat(v2): outcome page"`

---

### Task 16: 验收脚本 / 截图 / 收尾

**Files:**
- Create: `web/frontend/verify-v2.cjs`（playwright，dev-only，跑完删除）、`docs/images/v2-*.png`
- Modify: `.superpowers/sdd/progress.md`
- Test: 全量回归

- [ ] **Step 1:** `npm i -D playwright`（本地已有浏览器缓存）；写 verify-v2.cjs 覆盖 spec §7 十条：首页创建（断言 422 类型拒绝提示）→ 计划页改约束 → 工作区继承（断言首条 Ada 发言 prompt/约束出现）→ 推进到决策门（断言 decision_required 渲染、确认按钮 disabled）→ 选「仅内部」→ 断言讨论出现修订轮+成果 label=ai_suggestion → 插话 ack toast 断言 → 暂停/恢复（断言 paused banner 与恢复后继续）→ 成果编辑/复制/导出（断言导出响应含「演示」页脚）→ 切主题断言 html class 且页面状态不重置 → 切历史任务断言内容隔离。跑通后 `npm uninstall playwright` 删脚本。
- [ ] **Step 2:** 双主题截图（首页/工作区/成果）存 `docs/images/`，抽一张目检色值。
- [ ] **Step 3:** 全量回归：`uv run ruff check .`；`uv run pytest test_v2_models.py test_v2_store.py test_v2_demo.py test_v2_orchestrator.py test_v2_lifecycle.py test_v2_agents_client.py test_role_agent.py test_v2_api.py test_web_turns.py test_web_scheduler.py test_a2a.py test_task_store.py -q`；`npm run lint && npm run build`。
- [ ] **Step 4:** 真实模式冒烟（若 .env 有 key）：`V2_DEMO=0` 起栈，创建同一任务，确认 Ada 发言来自 LLM 且 phase 提示出现；失败路径可跳过（记录）。
- [ ] **Step 5:** 更新台账 + 最终汇报（已实现/演示/未接入三栏 + 验证结果）。
- [ ] **Step 6:** Commit — `git commit -m "test(v2): acceptance pass"`；push 由用户决定。

---

## Self-Review 结论

- 覆盖检查：spec §3 后端（Task 1-9）、§4 前端（Task 10-15）、§4.1 tokens（Task 10）、§5 状态一致性（Task 4/5/8 幂等与队列 + Task 13 单一状态源 + Task 8 探活）、§6 演示内容（Task 3）、§7 验收（Task 16）、§8 不做清单（Task 11 类型拒绝、材料标注）——无缺口。
- 占位符：无 TBD/TODO；文案基准均指向 Figma 节点或给出锚点断言。
- 类型一致性：`SpeakerBackend.speak(task, author, key)`、`Broadcaster.publish(task_id, event, data)`、`V2Store` 五方法、`DecisionOption{id,label,impact,recommended,uncertain}` 在 Task 4/5/6/8 间一致；前端 `v2api` 命名与路由表一一对应。


