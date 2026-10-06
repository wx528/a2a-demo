# 弹性专家席位（Guest Experts）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 spec `docs/superpowers/specs/2026-10-07-guest-experts-design.md` 实现"目的×专家正交"：专家注册表（内置预置+前端注册外部 A2A agent）、任务级 purpose 槽指派、orchestrator 按指派选人、custom 专家零人设注入、前端动态身份渲染。

**Architecture:** `web/v2/experts.py`（模型+SQLite 注册表+探活）；`/api/v2/experts` CRUD；V2Task 增 `experts` 快照与 `assignments` 固化（start 时校验写入）；orchestrator `expert_for(task, purpose)` 替换 `_AUTHOR_BY_KEY`，prompt 按 source 分流（builtin 人设 / guest 通用指令）；前端专家面板 + 计划页功能槽 + `roleMetaFromTask` 动态渲染。

**Tech Stack:** 沿用 V2 栈（FastAPI/Pydantic/sqlite3、React 19/Tailwind v4/lucide）。零新依赖。

## Global Constraints

- spec 2026-10-07 §2 决策：前端注册+DB；标签自动匹配+可改派；每槽一人；demo 模式改派禁用（防御性强制内置映射）。
- purpose 枚举固定：`research|propose|challenge|synthesize`；阶段映射：clarify→research、compare→propose、review→challenge、确认后 revise→propose、recommend→synthesize。
- 默认映射（零回归）：`ada→research、turing→propose、linus→challenge、sage→synthesize`。
- builtin 专家不可删除（409「内置专家不可删除，可禁用」）；URL/标签/emoji/启用可改。
- custom 专家 prompt **零人设注入**；输出约定（首行标题 ≤20 字、`# UNVERIFIED`）是约定非强制。
- 注册外部专家必须探活 `GET {url}/.well-known/agent-card.json`（2s 超时），失败 422 并回显原因。
- 注册表变更不追溯已创建任务（任务快照只读，spec §7.8）。
- 全中文 UI；Windows 下一律 Write/Edit 工具写文件；测试 `uv run pytest`（根目录扁平）+ `uv run ruff check .`；前端 `npm run lint && npm run build`。
- 每任务一 commit。

---

### Task 1: 专家模型与注册表存储

**Files:**
- Create: `web/v2/experts.py`
- Modify: `web/v2/models.py`（V2Task 增字段）
- Test: `test_experts_store.py`

**Interfaces:**
- Produces:
  - `PURPOSES: list[str] = ["research", "propose", "challenge", "synthesize"]`
  - `PURPOSE_LABELS: dict[str, str]`（研究/方案/挑战/权衡）
  - `PURPOSE_DUTIES: dict[str, str]`（spec §3.2 四条职能文案）
  - `PURPOSE_TAG_BY: dict[str, str]`（research→研究、propose→设计、challenge→挑战、synthesize→权衡）
  - `DEFAULT_ASSIGNMENTS: dict[str, str] = {"research": "ada", "propose": "turing", "challenge": "linus", "synthesize": "sage"}`
  - `class Expert(BaseModel)`：`id: str; name: str; url: str; tags: list[str] = []; emoji: str = "🔌"; source: Literal["builtin","custom"] = "custom"; enabled: bool = True; card_name: str = ""`
  - `BUILTIN_EXPERTS: list[Expert]`（ada 🧬 [研究] / turing 🧠 [设计,方案] / linus ⚡ [挑战] / sage ⚖️ [权衡]，url 指向 `http://role-<name>:801x`，source=builtin）
  - `class V2ExpertStore`：`__init__(db_path)`; `init()`（幂等 INSERT OR IGNORE 预置行）; `list_experts(enabled_only=False) -> list[Expert]`; `get_expert(id) -> Expert|None`; `create_expert(expert: Expert)`（id 冲突 → ValueError）; `update_expert(id, fields: dict) -> Expert`（不存在 → ValueError）; `delete_expert(id)`（builtin → ValueError）
  - `models.py`：`class TaskExpert(BaseModel)` `id,name,url,emoji,purpose,source`; `V2Task.experts: list[TaskExpert] = []`; `V2Task.assignments: dict[str, str] = {}`（public_dict 自动带出）；`V2Task.expert_by_id(eid) -> TaskExpert|None`

- [ ] **Step 1: 失败测试** `test_experts_store.py`

```python
import pytest
from web.v2.experts import (BUILTIN_EXPERTS, DEFAULT_ASSIGNMENTS, PURPOSES, V2ExpertStore)


def test_defaults_and_builtins():
    assert PURPOSES == ["research", "propose", "challenge", "synthesize"]
    assert DEFAULT_ASSIGNMENTS == {"research": "ada", "propose": "turing", "challenge": "linus", "synthesize": "sage"}
    assert len(BUILTIN_EXPERTS) == 4
    ada = next(e for e in BUILTIN_EXPERTS if e.id == "ada")
    assert ada.source == "builtin" and "研究" in ada.tags and ada.emoji == "🧬"


def test_crud_and_builtin_protection(tmp_path):
    s = V2ExpertStore(str(tmp_path / "db.sqlite")); s.init()
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
```

- [ ] **Step 2: 跑失败** — `uv run pytest test_experts_store.py -q`
- [ ] **Step 3: 实现** `web/v2/experts.py` + models 两字段（`assignments: dict[str, str] = Field(default_factory=dict)`）
- [ ] **Step 4: 通过** + `uv run pytest test_v2_models.py test_v2_store.py -q`（旧任务序列化兼容）
- [ ] **Step 5: Commit** — "feat(v2): expert registry store"

---

### Task 2: 专家 API `/api/v2/experts`

**Files:**
- Modify: `web/v2/routes.py`（新增路由 + 单例 `_EXPERT_STORE`，lifespan init）
- Test: `test_experts_api.py`

**Interfaces:**
- Produces:
  - `GET /api/v2/experts?enabled_only=` → `[{id,name,url,tags,emoji,source,enabled,card_name,probe}]`，probe ∈ up/down/unknown（并发探 card，2s 超时，与 connections 探活同款 `_probe` 逻辑复用）
  - `POST /api/v2/experts` `{name ≤40, url, tags ≤8 项各 ≤12 字, emoji?}` → 探活失败 422「无法连通该地址：{原因}」；成功落库（id=uuid8，source=custom，card_name 取 card.name 前 40 字）返回条目
  - `PATCH /experts/{id}` `{tags?/emoji?/enabled?/url?/name?}`（url 变更重探活，失败 422）
  - `DELETE /experts/{id}`（builtin → 409「内置专家不可删除，可禁用」）
  - ValueError → 404/409 与现有路由错误风格一致

- [ ] **Step 1: 失败测试** `test_experts_api.py`（fixture 复用 test_v2_api.py 的 env+reload 模式，V2_DB=tmp）

```python
def test_register_requires_reachable_card(client, monkeypatch):
    import web.v2.routes as r
    monkeypatch.setattr(r, "_probe_expert", lambda url: (False, "ConnectError"))
    resp = client.post("/api/v2/experts", json={"name": "Hermes", "url": "http://x:9", "tags": ["设计"]})
    assert resp.status_code == 422 and "无法连通" in resp.json()["detail"]


def test_register_list_patch_delete(client, monkeypatch):
    import web.v2.routes as r
    monkeypatch.setattr(r, "_probe_expert", lambda url: (True, ""))
    ok = client.post("/api/v2/experts", json={"name": "Hermes", "url": "http://x:9", "tags": ["设计"]})
    assert ok.status_code == 200
    eid = ok.json()["id"]
    assert ok.json()["probe"] == "up" and ok.json()["source"] == "custom"
    lst = client.get("/api/v2/experts").json()
    assert any(e["id"] == eid for e in lst) and any(e["id"] == "ada" for e in lst)
    assert client.patch(f"/api/v2/experts/{eid}", json={"enabled": False}).json()["enabled"] is False
    assert client.delete(f"/api/v2/experts/{eid}").status_code == 200
    assert client.delete("/api/v2/experts/ada").status_code == 409
```

（`_probe_expert(url) -> tuple[bool, str]` 为 routes 内可 monkeypatch 的探活函数；真实实现复用 connections 探活的 httpx 代码，抽出共用。）

- [ ] **Step 2: 跑失败** → **Step 3: 实现**（Probe 逻辑抽 `_probe_expert`，connections 路由改调用它）→ **Step 4: 通过**（`uv run pytest test_experts_api.py test_v2_api.py -q`）+ ruff
- [ ] **Step 5: Commit** — "feat(v2): experts API"

---

### Task 3: 编排接入 —— 指派固化与选人

**Files:**
- Modify: `web/v2/orchestrator.py`、`web/v2/agents_client.py`、`web/v2/routes.py`（start 固化）、`web/main.py`（lifespan init expert store）
- Test: `test_experts_orchestration.py`

**Interfaces:**
- Consumes: Task 1/2。
- Produces:
  - `experts.py`: `def resolve_assignments(requested: dict[str, str], store: V2ExpertStore) -> tuple[list[TaskExpert], dict[str, str]]` —— 校验 requested：purpose 合法、expert 存在且 enabled；不合法 purpose/专家 → 该槽回退默认映射；返回（出场快照 experts、最终 assignments）。快照含被指派的全部专家（去重）。
  - `agents_client.build_turn_prompt(task, author, key)` 签名不变，但身份段查 `task.expert_by_id(author)`：`source=="builtin"` → 现有人设段；`custom` → 「你是特邀专家。以你的专业经验就本次会议当前阶段发言：{PURPOSE_DUTIES[purpose]}」（purpose 由 key→stage→purpose 映射或直接传入——实现取 `STAGE_BY_KEY` 对应槽的 purpose）。
  - orchestrator：`_AUTHOR_BY_KEY[key]` 全部替换为 `expert_for(task, key)` —— key→purpose（clarify→research 等）→ `task.assignments[purpose]`（缺 → DEFAULT_ASSIGNMENTS）；`_make_turn` author 用该 id。demo 任务：`start` 固化时强制 `DEFAULT_ASSIGNMENTS`（防御）。
  - routes `POST /tasks/{id}/start`：StartRequest 增 `assignments: dict[str,str] | None = None`；preparing 校验后 `resolve_assignments` → 写 task.experts/assignments → save（原有约束/advanced 逻辑不变）。

- [ ] **Step 1: 失败测试** `test_experts_orchestration.py`

```python
import asyncio
import pytest
from web.v2.experts import Expert, V2ExpertStore, resolve_assignments
from web.v2.agents_client import build_turn_prompt
from web.v2.models import TaskExpert, V2Task


def test_resolve_assignments_fallback_and_snapshot(tmp_path):
    s = V2ExpertStore(str(tmp_path / "db.sqlite")); s.init()
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
async def test_orchestrator_uses_assignment(tmp_path):
    from web.v2.orchestrator import Orchestrator, NullBroadcaster
    from web.v2.store import V2Store

    seen = []
    class ProbeBackend:
        async def speak(self, task, author, key):
            seen.append((key, author))
            return (key, "b", False)

    store = V2Store(str(tmp_path / "db.sqlite")); store.init()
    t = _task_with_guest(); t.id = "t1"; t.status = "preparing"
    store.save_task(t)
    orch = Orchestrator(store, ProbeBackend(), NullBroadcaster())
    await asyncio.wait_for(orch.run_task("t1"), timeout=5)
    assert ("review_linus", "h1") in seen and ("clarify_ada", "ada") in seen
```

- [ ] **Step 2: 跑失败** → **Step 3: 实现**（orchestrator 加 `_PURPOSE_BY_KEY` 映射与 `expert_for`；prompt 分流）→ **Step 4: 通过**（新测试 + `uv run pytest test_v2_orchestrator.py test_v2_lifecycle.py test_v2_api.py -q` 全绿——现有测试用默认映射不应受影响）+ ruff
- [ ] **Step 5: Commit** — "feat(v2): purpose-based speaker resolution"

### Task 4: 前端 API + 专家管理面板

**Files:**
- Modify: `web/frontend/src/lib/v2api.ts`（experts 接口 + V2TaskT 增 experts/assignments）
- Create: `web/frontend/src/components/v2/ExpertPanel.tsx`（弹层面板）
- Modify: `web/frontend/src/components/v2/Shell.tsx`（侧栏「专家库」入口）
- Modify: `web/frontend/src/pages/PlanPage.tsx`（「管理专家」按钮入口挂载面板）
- Test: `npm run lint && npm run build`

**Interfaces:**
- `v2api`：`ExpertT {id,name,url,tags,emoji,source,enabled,card_name,probe}`；`listExperts(enabledOnly=false)/addExpert({name,url,tags,emoji?})/updateExpert(id,patch)/deleteExpert(id)`；`V2TaskT` 增 `experts: TaskExpertT[]; assignments: Record<string,string>`；`startTask` body 增 `assignments?: Record<string,string>`
- `ExpertPanel`：props `{open, onClose, onChanged?}`——弹层（overlay + 卡片，Esc 关）：列表行（emoji+name+「内置」标+url 截断+tags chips+探活徽标 青在线/红离线/灰未知+启用 switch+删除/禁用）+ 添加表单（名称/地址/标签 chips 多选含自由输入/可选 emoji）；提交成功 toast「专家已注册」、422 展示 detail；每次打开拉 `listExperts()`，操作后刷新

- [ ] **Step 1:** v2api 扩展 + ExpertPanel + 两处入口
- [ ] **Step 2:** lint+build 绿
- [ ] **Step 3:** Commit — "feat(v2): expert panel"

---

### Task 5: 计划页功能槽与改派

**Files:**
- Create: `web/frontend/src/components/v2/PurposeSlots.tsx`
- Modify: `web/frontend/src/pages/PlanPage.tsx`
- Test: lint+build

**Interfaces:**
- `PurposeSlots`：props `{task（读 experts 快照——preparing 任务 start 前已有默认快照？否：**创建时后端即写入默认快照**，见 Task 3 的 routes start——修正：`POST /tasks` 创建时即调 resolve_assignments({}, store) 写入默认快照，start 时再按请求覆盖）, assignments, onAssign(purpose, expertId), experts: ExpertT[], demo, onManage()}`。四槽（研究/方案/挑战/权衡）：胶囊=emoji+name+职能一句话（PURPOSE_DUTIES）；每槽下拉（原生 select 语义，样式统一）候选=enabled 专家（tags 命中 purpose 中文标签者排前，组名「标签匹配」/「全部专家」）；demo → 下拉 disabled + 底部提示条「演示模式使用内置专家脚本」；槽底「+ 添加专家」按钮 → onManage()
- PlanPage：state `assignments`（初值 task.assignments）；开始协作 body 带 assignments；右卡原有 RoleDuties 替换为 PurposeSlots（RoleDuties 删除或保留给专家管理面板的说明区——决策：删除，其人设说明合并进 PurposeSlots 的内置专家 tooltip）

- [ ] **Step 1:** PurposeSlots + PlanPage 接线（含 POST /tasks 创建即写默认快照的后端一行——若 Task 3 未含则此处补测试）
- [ ] **Step 2:** lint+build；dev 手验：下拉改派 → 开始协作 → 工作区 meetings 显示新专家
- [ ] **Step 3:** Commit — "feat(v2): purpose slots with reassignment"

---

### Task 6: 动态身份渲染

**Files:**
- Modify: `web/frontend/src/lib/roles.ts`、`TurnCard.tsx`、`MeetingPod.tsx`、`OutcomeOverview.tsx`、`OutcomePage.tsx`（依据行/确认行）、`UserNoteCard.tsx`（不动）、`web/v2/routes.py`（export 署名）
- Test: lint+build + 手验

**Interfaces:**
- `roles.ts` 新增：`roleMetaFromTask(task, expertId): {emoji, zh, en}` —— 查 task.experts 快照（name 拆「中文名 · 英文名」；builtin 无拆分时 zh=name/en=id）；fallback 内置静态表；再 fallback `🔌 未知专家`。**保留现有 roleMeta 供 demo/内置兼容路径**。
- 消费点：TurnCard/MeetingPod/OutcomeOverview/OutcomePage 依据行把 `roleMeta(author)` 改为 `roleMetaFromTask(task, author)`（各组件需能拿到 task——已是 props 的直接用，否则加 prop）；MeetingPod 的 POD_ROLES 从固定四改为 `task.assignments` 排序出的四位（purpose 顺序 research/propose/challenge/synthesize）；含 custom 专家时 podHeader 追加「· 含 N 位外部专家」
- export（routes.py）：署名行改用 task.experts 快照名

- [ ] **Step 1:** roles.ts + 各消费点切换
- [ ] **Step 2:** lint+build；dev 验证：内置默认任务渲染与之前一致（零回归目检）+ 指派 guest 后署名正确
- [ ] **Step 3:** Commit — "feat(v2): dynamic identity rendering"

---

### Task 7: 验收与回归

**Files:**
- Create: `web/frontend/verify-guests.cjs`（临时，跑完删）
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1:** 全量后端回归 `uv run ruff check .` + 13 个测试文件 `-q` 全绿；前端 lint+build 绿
- [ ] **Step 2:** E2E（本地）：起 web（demo 模式）+ 起第二个 role_agent 实例扮演假 hermes（`ROLE=sage PORT=8014` 即可冒充，或真实模式跑真 LLM）；API 注册专家（探活通过）→ 创建任务 start 带 `{"challenge": "<新专家id>"}` → 轮询至门 → 断言 review 阶段发言 author=新专家 → 确认 → 成果署名正确；不连通 URL 注册 422；demo 任务 assignments 被强制内置
- [ ] **Step 3:** playwright 脚本覆盖（可选，如时间允许）：计划页改派 → 开始 → 断言；跑完删脚本 + `npm uninstall playwright`
- [ ] **Step 4:** 更新台账；最终汇报（已实现/未接入）
- [ ] **Step 5:** Commit — "test(v2): guest experts acceptance"

---

## Self-Review 结论

- 覆盖：spec §3 模型（Task 1）、§4 API（Task 2）、§5 编排+prompt+demo 防御（Task 3）、§6.1 面板（Task 4）、§6.2 功能槽（Task 5，含创建即写快照的补充决策）、§6.3 动态渲染（Task 6）、§7 一致性（Task 3 fallback + 快照只读语义）、§9 验收（Task 7）。§8 不做清单未引入。
- 占位符：无 TBD；前端任务给出精确 props/行为，后端给出完整测试代码与签名。
- 类型一致：`resolve_assignments(requested, store) -> (experts, assignments)`、`expert_for(task, key)`、`roleMetaFromTask(task, expertId)`、`_probe_expert(url) -> (bool, str)` 在 Task 2-6 间一致；Task 5 依赖 Task 3 的"创建即写默认快照"已在 Task 3 routes 范围内写明。
