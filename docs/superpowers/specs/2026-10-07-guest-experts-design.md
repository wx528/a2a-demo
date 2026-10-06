# A2A 会议室 · 弹性专家席位（Guest Experts）设计文档

日期：2026-10-07
状态：已与用户逐节确认（前端注册+DB / 目的槽自动匹配+可改派 / 每槽一人）
前置：基于 V2 决策工作区（spec 2026-10-04-v2-decision-workspace-design.md），V2 流程与决策门不变。

## 1. 核心理念

**目的（功能位）与专家（身份）正交**：会议流程固定需要四个发言目的——研究（research）/ 方案（propose）/ 挑战（challenge）/ 权衡（synthesize）；由谁坐这个位置是可编排的。专家可以是内置角色 agent，也可以是任何 A2A 兼容的外部 agent（自带 memory/检索），其经验积累完全是它自己的事——框架只发"目的指令 + 会议上下文"，不覆盖外部专家的人设。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| 专家来源 | 前端注册 + SQLite 存储；内置四专家为预置行 |
| 目的×专家映射 | 按标签自动匹配，计划页可改派（下拉） |
| 同槽人数 | 每槽一人（首版） |
| 演示模式 | 改派禁用，固定使用内置专家脚本（诚实标注） |

## 3. 数据模型

### 3.1 专家注册表 `web/v2/experts.py`（新模块：models + store + probe）

`experts` 表（SQLite，同 v2_tasks.db 或独立 experts.db——用同一个 v2_tasks.db，表 `experts`）：
- `id`：slug（内置固定 `ada/turing/linus/sage`；custom 用 uuid8）
- `name`：显示名（custom 必填；builtin 固定 中文名 · 英文名）
- `url`：A2A 服务基址（内置 = 本地容器地址，可编辑）
- `tags`：JSON 数组，取值 ⊆ {研究, 设计, 挑战, 权衡, 数据, 评审, 其他…}（自由字符串，UI 提供常用 chips）
- `emoji`：可选，默认内置四角色沿用 🧬🧠⚡⚖️，custom 默认 🔌
- `source`：`builtin | custom`
- `enabled`：bool
- 预置行由 `init()` 幂等写入（INSERT OR IGNORE），tags：ada=[研究]、turing=[设计, 方案]、linus=[挑战]、sage=[权衡]

接口（`V2ExpertStore`）：`init / list_experts / get_expert / upsert_expert / update_expert / delete_expert`。builtin 不可删除；url 可改（比如指向外部）。

### 3.2 任务快照

`V2Task` 增加：
- `experts: list[TaskExpert]` —— 本次出场专家快照：`{id, name, url, emoji, purpose, source}`（注册表变更不影响已创建任务）
- `assignments: dict[str, str]` —— purpose → expert_id（research/propose/challenge/synthesize → 各一人）

purpose 常量 `PURPOSES` 与职能文案：research=核实事实与不确定性 / propose=提出可执行方案 / challenge=检查风险与隐含假设 / synthesize=整理权衡与建议。
阶段映射固定：clarify→research、compare→propose、review→challenge、决策确认后（revise/recommend）→propose 与 synthesize。
默认 assignments（无注册专家时）：ada→research、turing→propose、linus→challenge、sage→synthesize（**内置路径零回归**）。

### 3.3 序列化兼容

旧任务无 experts/assignments 字段 → pydantic 默认（experts=[]，assignments={}）→ 运行时 fallback 到默认内置映射；`public_dict` 照常输出两字段。

## 4. 专家 API（`/api/v2/experts`，additive）

- `GET /experts` → 列表（含 `probe: "up"|"down"|"unknown"`，后台 2s 探 card，聚合并发）
- `POST /experts` `{name, url, tags[], emoji?}` → 探 `GET {url}/.well-known/agent-card.json`（2s）；失败 → 422 `{"detail": "无法连通该地址：<原因>"}`；成功 → 读取 card 的 name 存为 `card_name`（展示用副标题），落库返回
- `PATCH /experts/{id}` `{tags?/emoji?/enabled?/url?/name?}` → url 变更时重新探活；builtin 仅允许 url/tags/emoji/enabled
- `DELETE /experts/{id}` → 仅 custom（builtin 删除 → 409「内置专家不可删除，可禁用」）
- 请求模型：name ≤40 字、url http(s)、tags ≤8 项各 ≤12 字

## 5. 编排与 prompt（`orchestrator.py` / `agents_client.py`）

- `_AUTHOR_BY_KEY` → 改为 `expert_for(task, purpose)`：查 `task.assignments[purpose]` → task.experts 快照；缺失/禁用 → 内置默认链 fallback（assignments 缺 purpose → 默认内置 id）。
- Turn.author = **expert_id**（快照内 id 全局唯一）。
- `build_turn_prompt(task, expert, key)`：身份段按 source 分流——
  - builtin：沿用现有四角色人设 + 原有指令；
  - custom：`你是特邀专家。以你的专业经验就本次会议当前阶段发言：{purpose 指令}` + 目标/期望成果/约束/近期讨论（同现有结构），**不注入任何人设**。
- 输出约定（对外部 agent 是约定非强制）：首行 ≤20 字为观点标题、`# UNVERIFIED` 标待验证；不合约定整段作正文（现有 `_split_turn_text` 已兼容）。
- 流程/决策门/暂停恢复/成果组装**全部不变**；`turn_start` 事件带 `author=expert_id`。
- demo 模式：改派被 UI 禁用；后端防御——demo 任务的 assignments 强制内置映射（即使快照被篡改也走脚本）。

## 6. 前端

### 6.1 专家管理面板（新组件 `ExpertPanel`）

- 入口：计划页右卡「管理专家」按钮 + 首页侧栏「专家库」入口（挂 Shell 侧栏底部区）
- 列表：emoji+名称（builtin 带「内置」小标）+ url 截断 + tags chips + 探活徽标（在线=青 / 离线=红 / 未知=灰）+ 启用 toggle + 删除（builtin 隐藏删除、显示「禁用」）
- 添加表单：名称、A2A 地址、标签多选 chips（研究/设计/挑战/权衡 快捷 + 自由输入）、可选 emoji；提交后即时显示探活结果，失败 422 展示原因
- `v2api` 增 `listExperts/addExpert/updateExpert/deleteExpert`

### 6.2 计划页「本次出场专家」

右卡改为四个**功能槽**（研究/方案/挑战/权衡）：每槽胶囊显示当前指派专家（emoji+名），下拉改派（候选=enabled 专家，按 tags 命中 purpose 优先排序，无匹配显示全部启用专家并注「无标签匹配」）；槽底「+ 添加专家」开面板；demo 模式下拉禁用 + 提示条「演示模式使用内置专家脚本」。
`start` 请求体扩展：`assignments: {purpose: expert_id}`（缺省 → 默认映射）。

### 6.3 动态身份渲染

- `roles.ts` 新增 `roleMetaFromTask(task, expertId)`：优先查 task.experts 快照，fallback 内置静态表（unknown expert → 🔌 未知专家）
- 消费点全部切换：TurnCard 头像/署名、UserNoteCard（不变，user 固定）、MeetingPod 胶囊（改为渲染 task.experts 的四位，非固定四）、决策确认条、OutcomeOverview 确认行、OutcomeRail 依据行、HomePage RecentTasks（不涉专家）、export Markdown（署名用专家名）
- MeetingPod 汇总行：demo/内置照旧；含 custom 专家时显示「含 N 位外部专家」

## 7. 状态一致性（沿用 V2 七条，新增两条）

8. 专家注册表变更不追溯已创建任务（任务快照只读）；运行中的任务始终使用其快照。
9. 指派槽必须指向 enabled 且在快照内的专家；快照固化时校验，失败 → 默认内置链。

## 8. 明确不做

不做同槽多专家；不做外部 agent 的输出结构化解析（按纯文本流约定）；不做专家评分/自动淘汰；不做 demo 模式的 guest 脚本；内置专家暂不做完整 CRUD UI（仅 url/tags/emoji/启用）。

## 9. 验收

- pytest：experts CRUD+探活 mock、assignments 固化与 fallback、orchestrator 按 assignments 选人、custom prompt 无 persona 注入、demo 防御（assignments 被改仍走内置）、内置默认路径回归（现有全绿）
- 交互：注册外部 agent（可用本地 role_agent 起一个"假 hermes"）→ 派到挑战槽 → 工作区显示其名与发言 → 成果署名正确；demo 模式改派禁用；不连通地址注册被拒
- 回归：V2 验收 10/10（内置默认路径）
