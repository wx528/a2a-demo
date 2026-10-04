# A2A 会议室 V2 · 决策工作区 设计文档

日期：2026-10-04
状态：已与用户逐节确认（V2 替换 V1 / 独立角色容器 / web 进程内编排 / 全局演示模式）
设计来源：Figma `LFuyC9RMLRX8Z8KHN4APUs` 五画面（目标首页 14:3150、协作计划 14:3299、决策工作区 14:3496、决策工作区夜间 14:3970、决策成果 14:3739），桌面基准 1440。

## 1. 产品定位

V2 不是"观看多个 AI 轮流聊天"，而是：组织不同专业视角，帮助用户完成一次判断并形成可用成果。
主流程：提出目标 → 确认协作计划 → 自动讨论 → 关键节点用户介入 → 形成成果。
品牌保留「A2A 会议室」，全中文界面；协议名、人名、专业缩写可英文。
本轮只完整实现「做出决策」目标路径；其余三类目标明确提示暂不支持。
统一演示任务：判断团队是否需要引入 A2A（约束：已有内部 MCP 工具接入 / 首阶段优先私有化 / 只验证一个跨团队协作场景）。

## 2. 已确认决策

| 决策点 | 结论 |
|---|---|
| V1/V2 关系 | V2 替换 V1 前端；V1 后端路由保留不删但 UI 不暴露 |
| 角色驱动 | Ada/Turing/Linus/Sage 各为独立 A2A agent 容器（协议面完整） |
| 编排位置 | web 进程内 `web/v2/` 模块持有任务状态机；角色容器无状态 |
| 演示模式 | 全局：启动无 LLM key 或 `V2_DEMO=1` 时进入，整站明确标注；真实模式 LLM 失败报错+重试，绝不静默用脚本内容冒充 |

## 3. 后端架构

### 3.1 `web/v2/` 新包

- **models.py**：`V2Task`（goal_type=decision｜research/compare/review(暂不支持)、goal_text、expected_outcome、constraints[]（含 confirmed 标记）、materials[]（name+text，仅登记文本）、advanced{mode,rounds}、status、current_stage、pending_decision、outcome、demo:bool）、`Turn`（seq、stage、author(role|user|system)、kind(statement|user_note|decision_record|system)、title、body、verified:待验证标记）、`Decision`（question、options[{id,label,impact,recommended}]、chosen_id|null、status）、`OutcomeDoc`（conclusion、summary_groups{confirmed,disputed,unverified}、reasons[{title,body,refs[]}]、path_comparison[2]{name,desc,pros,cons,fit,recommended?}、evidence[{seq_ref,stage,author,quote}]、open_questions[]、actions[{title,detail,assignee:"待分配",due:"待确定"}]、acceptance[{title,detail}]、label ∈ 讨论草稿/AI 协作建议/团队已确认）
- **store.py**：SQLite 单库（`v2_tasks.db`）：tasks/turns/decisions/outcome 表；创建幂等；历史列表含状态；演示与真实任务同库、以 `demo` 字段隔离。
- **orchestrator.py**：唯一状态机。任务状态枚举：`preparing(准备中) → running(进行中) ⇄ waiting_confirmation(等待确认) / paused(已暂停) → completed(已完成) / failed(失败)`。阶段固定：`clarify 澄清需求 → compare 比较方案 → review 评审风险 → recommend 形成建议`。
  - 普通发言自动推进（无需用户点"继续"）；每阶段按角色顺序发言（Ada→Turing→Linus→(Sage)），发言间插入已有用户约束回顾。
  - 决策门：进入 review 阶段、Linus 风险发言完成后触发 `decision_required`。默认决策题与选项写死在任务模板（见 §6），`recommended` 仅作展示标签。
  - 确认路径：用户选择选项 → 该选项写入已确认约束（append 用户 decision_record turn，#编号连续）→ 状态回到 running → Turing 按新约束修订试点路径 → Sage 汇总权衡形成建议 → 进入 recommend 阶段 → 完成 → 成果文档定稿（label=AI 协作建议）。
  - 「暂不确定」：追加一轮"继续比较影响"（Turing+Linus 各一条），随后重新弹出同一决策门；绝不视为批准。
  - 暂停/恢复：`paused` 时编排器不再产生任何发言；恢复从断点继续。
  - 失败/重试：真实模式下单条发言 LLM/agent 调用重试一次后仍失败 → 任务 `failed`（保留已完成发言），提供重试按钮（重发该 turn）。
  - 防重：同一任务同时只允许一个活动编排协程；决策门未决时自动推进挂起；介入消息入队，在当前发言结束后依序处理并 ack。
- **agents_client.py**：复用 shared JSON-RPC 客户端；`SendStreamingMessage` 到 `http://role-<name>:801x/rpc/stream`；输入 data part：阶段指令、目标、期望成果、约束（含已确认）、决策记录、近 N 条发言、输出要求（观点标题+正文，可带 verified 标记）；token 增量经 SSE `message_delta` 转发；`turn_done` 带 seq。
- **demo.py**：确定性脚本。统一演示任务＝Figma 全套内容（#01–#06 发言、决策门三选项、确认后修订与建议、成果文档）。其他目标文本：参数化模板（嵌入用户目标/约束的原句）走同一阶段与决策门（决策题退化为"是否按上述约束推进试点？"）。演示任务不发起任何 agent/LLM 调用。
- **routes.py**（`/api/v2`）：
  - `POST /tasks`（goal_type、goal_text、expected_outcome、constraints[]、materials[]、advanced）→ 任务+计划草稿，status=preparing
  - `GET /tasks`（历史：id、标题、状态、阶段、成果摘要、demo 标记）、`GET /tasks/{id}`（全量：turns、decision、outcome、agent 连接真态）
  - `POST /tasks/{id}/start`（确认计划，可携带修改后的约束/角色微调）→ running
  - `POST /tasks/{id}/decisions/{did}` {option_id}；`POST /tasks/{id}/interventions` {intent: 追问|补充条件|调整方向, text} → 立即 ack（SSE `intervention_ack`：已接收+预计处理时点）
  - `POST /tasks/{id}/pause|resume|retry`；`POST /tasks/{id}/end`（提前结束：基于已有内容即时定稿）
  - `GET /tasks/{id}/stream`（SSE：message_delta/message_abort/stage_change/decision_required/intervention_ack/status_change/outcome_update）
  - `GET /tasks/{id}/outcome`、`PATCH /tasks/{id}/outcome`（编辑保存；label 保持 AI 协作建议，编辑不改变审批语义）、`GET /tasks/{id}/export`（Markdown 附件，演示任务页脚注明演示内容）

### 3.2 角色容器 `role_agent/`（新服务，一份代码 ×4 实例）

- compose 服务：`role-ada/:8011`、`role-turing/:8012`、`role-linus/:8013`、`role-sage/:8014`，env `ROLE=`。
- 协议面与现有 agent 一致：`GET /.well-known/agent-card.json`（含 name/description/skills，按角色注入人设）、`POST /rpc`、`POST /rpc/stream`；JSON-RPC 2.0、camelCase、SSE 增量。
- 无状态执行器：按消息内的阶段指令与人设生成发言；内部复用 `shared/llm_client.py`（max_tokens=8000、失败重试一次）与 `shared/agent_loop.py`（检索→起草→自审→修订，`[PHASE]` 标记由 web 侧转成阶段提示）。
- 四角色人设（写入 system prompt 与 agent card）：Ada 研究员🧬核实事实与不确定性；Turing 方案设计师🧠提出可执行方案；Linus 挑战者⚡检查风险与隐含假设；Sage 决策助手⚖️整理权衡与建议（不代替用户决定）。

### 3.3 V1 兼容

`/api/meetings` 等旧路由与 research/writing/debate/orchestrator 容器保留运行（协议演示），前端不再引用；`web/frontend` 中 V1 组件移除。

## 4. 前端

技术栈延续 React+Vite+CSS 变量双主题；新增依赖仅 `lucide-react`、`@fontsource` Noto Sans SC / JetBrains Mono（打包进镜像，无字体 CDN）。路由：无依赖 hash 迷你路由（`#/`、`#/plan`、`#/task/:id`、`#/task/:id/outcome`）。`v2-theme` localStorage，**默认浅色**，切换不丢任务状态（状态源在后端+内存 SSE 重连）。

四页（按 Figma 逐屏实现，1440 基准；<1024px：侧栏收抽屉、成果栏下堆叠、计划卡纵排）：

1. **目标首页**：品牌侧栏（开始新任务/任务与成果历史/全部成果入口/工作区信息）+ 顶栏（标题、团队私有工作区徽标、主题切换）。主区：引导语 + 四目标卡（做出决策高亮可选；其余点击弹提示"本轮暂不支持，已为你锁定做出决策路径"）+ 问题输入卡（目标问题、约束说明、添加材料=粘贴文本+文件名，标注"仅登记文本，不做文档解析"；生成协作计划按钮）+ 流程说明行 + 最近成果列表（状态徽标：讨论中/待确认/已完成；行操作：回答并继续/查看成果/进入讨论）。
2. **协作计划**：步骤指示「✓ 目标与材料 → 2 确认计划」；左卡=要做出的判断/期望成果/上下文约束（可增删改，改动继承工作区）/材料摘要（＋添加）；右卡=四角色职责行（emoji 头像+中文名+英文名+职责）+ 人类决策边界青条；下方「讨论如何走向成果」4 阶段卡（03 卡高亮"关键节点请你确认"）；高级设置折叠（模式/轮数；不支持的选项禁用+说明）；返回上一步 / 开始协作。
3. **决策工作区**：顶栏（任务名、阶段·N/4、状态徽标、结束协作、主题切换）→ 辅助会议舱（可收起：标题行+四角色状态胶囊，实时显示 发言中/等待确认/已完成）→ 三栏：中 800px「围绕目标的讨论」卡（阶段进度 4 格；当前阶段分组头+说明；发言卡=emoji 头像+角色+姓名+#编号+观点标题+正文（流式）+可选"待验证"琥珀标记；关键决策确认卡=紫底「需要你确认」+问题+建议说明（"这是建议，尚未替你确认"）+三选项卡（radio 语义，建议项带徽标）+确认按钮未选置灰+底部影响说明；用户补充约束青色条；此后阶段分组头"已完成·保留关键发言"）+ 介入输入区（意图 chip 追问/补充条件/调整方向 + 输入 + 发送；ack 行"已接收·将在当前发言结束后处理"；说明行"补充内容会加入讨论；关键选择仍需在上方确认"）。右 336px 成果草稿栏（标题"成果草稿"+说明"随讨论更新·尚未形成最终建议"；已确认/仍有分歧/待验证三组（青/紫/琥珀左边线）；建议草稿预览卡（初步建议+正文+方案待定说明+预期验证框+草稿依据）；底部分隔线+完成提示+来源提示）。
4. **决策成果**：顶栏（决策成果、任务名·已完成协作·第4/4阶段；编辑成果/复制/导出）。概览大卡（AI 协作建议·待团队审批徽标、主结论 H1、结论说明、分隔线、「✓ 你已确认：首轮仅内部 Agent·#05」+ 琥珀"协作已完成，不代表方案已验证或审批通过"）。正文 780px：01 为什么是内部试点（建议理由×3，各带"关联讨论 #xx ↗"跳转）；02 两条可行路径（对比双卡，建议路径徽标）；03 回到讨论（依据列表=编号·阶段/发言者/摘要/↗；顶部注明"以下为本次讨论记录，不是外部文献或已验证事实"）；04 把建议变成下一步（行动项×3，责任人待分配·时间待确定）。右栏 320px：仍需解决的问题（琥珀卡+继续讨论按钮→回工作区）；通过这些条件再扩展（验收条件卡+停止条件）；审批说明（"本页为 AI 协作建议，需团队审批"）。成果尾注：返回讨论 / 建议性质声明。

### 4.1 视觉 tokens

浅色（默认）：bg `#f7f7f4`、侧栏 `#eeefef`、边 `#dfe2e5`、卡 `#ffffff`、文 `#242735/#515665/#797e8a`、紫 `#7054d8`（软底 `#f0ecfc`/边 `#d7ccf4`）、青 `#167e87`（底 `#e9f5f4`）、琥珀 `#996619`（底 `#fbf3e4`/边 `#eed9b1`）、灰片底 `#f0f1f0`、页面阴影 `0 8px 28px rgba(37,42,64,.06)`。
暗色：bg `#141720`、侧栏 `#171b25`、卡 `#1b1f2b`、面 `#242937`、边 `#333a4b`、文 `#e9eaf2/#c0c5d2/#959eaf`、紫 `#8060d9`（边 `#aa91ff`；软底 `#2c2544`/边 `#544272`，文字 `#aa91ff`）、青 `#6bcbd0`（底 `#1c353c`）、琥珀 `#e8bd77`（底 `#352d23`）。
字体：Noto Sans SC 400/500/700 + JetBrains Mono（A² 字标、#编号、阶段序号）。状态一律"文字+颜色"双编码；全部交互态（hover/active/disabled/focus-visible/loading/empty/error/提交反馈）落地；键盘：radio 组、Enter 提交、Esc 关抽屉、焦点环。

## 5. 状态一致性规则（硬性）

1. 六状态唯一来源=orchestrator；消息、会议舱、阶段进度、成果摘要、历史列表全部读同一份任务状态。
2. `waiting_confirmation`/`paused` 时无任何 agent 发言；演示模式同样遵守。
3. 决策未经用户点击不得进入已确认约束；"暂不确定"必须走追加比较后重问。
4. 结束协作/完成任务 ≠ 团队审批；成果 label 只能由用户显式编辑为"团队已确认"。
5. 防重复：创建/确认/选项提交幂等（重复请求返回当前态）；介入消息排队不并发注入。
6. 任务隔离：turns/decisions/outcome 均挂 task_id；前端切换任务即切换 SSE 订阅，不串台。
7. 连接指示反映真实：真实模式显示各 role 容器 agent-card 探活结果；演示模式显示"演示·非实时"，不伪装在线。

## 6. 统一演示任务内容基准

题目：首轮试点是否允许连接外部 Agent？选项：仅内部 Agent（建议·保持私有化边界）/ 允许受控外部接入（追加外部信任与授权评审）/ 暂不确定（先补齐判断所需信息）。默认建议=仅内部，必须用户确认。
确认后状态（用户已选"仅内部"）：结论=建议开展内部小范围试点，暂不全面引入 A2A；理由×3、方案对比（保持现状 vs 内部试点）、依据 #01/#03/#04/#05/#06、未解决问题×3、行动项×3、验收条件（任务交接可追踪 / 取消与失败恢复可控 / 工具授权不被绕过）+停止条件。全部文案以 Figma 画面文字为准（demo.py 逐字脚本化）。

## 7. 验收

- pytest：状态机全迁移（自动推进、决策门、暂不确定分支、暂停恢复、失败重试、提前结束）、幂等/防重、任务隔离、导出内容、演示确定性（同一输入两次运行输出一致）、真实/演示互斥。
- playwright 交互脚本：首页创建→计划页改约束→工作区继承→推进到决策门→选择→讨论与成果同步→插话 ack→暂停/恢复/失败重试状态一致→成果编辑/复制/导出→切主题/切历史不丢状态。
- 目检：双主题 + 1440/1024/390 三档宽度无溢出遮挡。
- 交付汇报分三栏：已实现 / 演示模式 / 尚未接入（如：材料文档解析、其他三类目标路径、团队多用户审批流）。

## 8. 明确不做的

不做其他三类目标（研究/比较/评审）的完整流程；不做文档内容解析（材料仅登记文本）；不做多人账号与审批工作流；不虚构引用、验证结果、负责人、日期（责任人/时间一律"待分配/待确定"）。
