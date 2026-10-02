# 「夜间指挥舱」UI 重构设计文档（Figma 稿实现）

日期：2026-10-03
状态：已与用户确认
视觉标准：Figma 文件「A2A 会议室」6 画板（设计 Tokens / 关键组件状态 / 夜间指挥舱 / 浅色指挥台 / 新建会议 / 空状态首页）

## 背景与目标

当前 shadcn 中性色版本功能完整但视觉平淡。按 Figma 设计稿把前端重构为「AI 指挥舱」风格：暗色为主、紫色霓虹、mono 技术标签、网格纹理。布局同时按设计稿重构（右栏、双栏弹窗、仪式感步进条）。hooks 架构、API/SSE 协议、业务行为不变。

## 已确认的决策

1. **完整按设计稿重构**（布局 + 视觉）。
2. **右栏数据全部真实可算**，不展示任何假数字。
3. **「允许观众质询」后端加字段做真**（唯一后端改动，additive、默认值兼容）。
4. **默认暗色「夜间指挥舱」+ 保留亮色「指挥台」+ 跟随系统 + 手动切换**。
5. 设计稿中 Ada/Linus/Turing/Sage 为示例文案，实现使用后端真实人格（socrates/hume/kant/nietzsche/skeptic_engineer/vc + judge）。

## 设计 Tokens（来自 Figma「设计 Tokens」画板，精确值）

### 颜色
| Token | 暗色 | 亮色 |
|---|---|---|
| bg | `#070A12` | `#F1F3F9` |
| surface（面板） | `#0E1423` | `#FFFFFF` |
| raised（浮起） | `#151C2E` | `#FFFFFF` + 边框 |
| border | `#263049` | `#E2E6F0`（浅色边框为推导入的浅灰） |
| text-primary | `#F2F5FF` | `#15192A` |
| text-secondary | `#A8B1C7` | `#4A5468`（推导） |
| text-muted | `#69748D` | `#8891A5`（推导） |
| primary | `#745CFF` | 同色 |
| assist/cyan | `#32D6E8` | `#0EA5B5`（亮色下加深保对比，推导） |
| success | `#35D07F` | 同色 |
| warning/judge | `#F6B84A` | 同色 |
| danger | `#FF6680` | 同色 |

网格纹理：`#263049` 1px 线、80px 间距、约 18% 不透明度，仅暗色启用（CSS repeating-linear-gradient 实现）。

### 字体
- Sans：`Inter`（Google Fonts）+ `"HarmonyOS Sans SC", "PingFang SC", "Microsoft YaHei"` 回退；标题 800 / 正文 400。
- Mono：`JetBrains Mono`（Google Fonts）+ `ui-monospace` 回退；技术标签 10–12px、tracking +0.08em。
- 字号：Display 36 / H1 28 / H2 20 / H3 16 / Body 14 / Small 12。

### 圆角 / 阴影 / 间距
- 圆角：XS 6 / SM 10 / MD 14 / LG 20 / XL 28。
- 阴影：SOFT `0 10px 30px rgba(17,22,42,0.08)`；GLOW `0 0 18px rgba(116,92,255,0.33)`（焦点与实时状态）。
- 间距：4 / 8 / 12 / 16 / 24 / 32 / 48 / 64。

## 布局与组件映射

### Sidebar
- 品牌区：方形 A² 标志（primary 渐变）+ 「A2A 会议室」+ mono 小字标语。
- 「新建会议」primary 按钮（GLOW 阴影 hover）。
- 「最近会议」列表：选中项 primary 描边 + raised 底；每项主题 + mono 元数据（模式 · 时间）。
- 底部系统状态：绿点 + 「服务在线」+ 说明文字（由 `useMeetings` 最近一次拉取成败驱动，真实状态）。

### HeroHome（原 HomeEmptyState）
- 青色 mono 眉题 `INITIALIZE MULTI-AGENT SESSION` → 改为中文语境保留英文眉题（设计如此）。
- Display 大标题「让多个 AI Agent 围绕一个主题真正交锋」+ 副标题。
- 「发起第一次会议」主按钮；下方 01 顺序编排 / 02 实时插话 / 03 自动总结 三特性行。

### RoomHeader
- 返回按钮 + 主题（H2）+ mono 会话编号（`SESSION {meeting.id}`，真实 id）+ 模式 Badge。
- 右侧：绿点 + 实时连接状态（保留现有 connected 语义）。

### ParticipantBar
- mono 小标 `AGENTS` + Agent 胶囊：emoji 头像 + 名字 + 彩色状态点/文字（等待中灰、思考中 primary、发言中 success）。

### TurnControlBar（仪式感）
- 左：⚡ 图标方块（primary 底）+ mono 眉题 `NEXT SPEAKER · ROUND x/N`（真实推导，见下）+ 发言者 emoji 名字。
- 右：自动连播 Switch + 「继续」按钮（GLOW 阴影）。
- roundtable/pipeline 时眉题显示对应文案；推导不出轮数时只显示 `NEXT SPEAKER`。

### RightRail（新增，会议室右侧 280px，<lg 屏幕隐藏）
- **轮次进度**：前端移植 `turns.build_sequence` 为 `src/lib/sequence.ts`（纯函数），用 `meeting.turn_state.seq_index` + `meeting.mode/max_rounds/pro_persona/con_persona` 推导每个槽位（done ✓ / 当前高亮 / pending），映射到参与方名。pipeline 耗尽后用户插话触发的重置由服务端 `turn_state` 天然反映。
- **SESSION TELEMETRY**：消息数（`messages.length`）、讨论字数（agent 消息 content 长度合计）、延迟（SSE `init` 事件实测往返耗时，hook 内测量）、各参与方消息数迷你柱状图（纯 div 高度，无图表库）。
- 全部真实数据；推导不出就不显示该项。

### MessageBubble / MessageList
- Agent 消息：头像 + 名称 + 角色标签（正方/反方/主持等，mono 小字）+ 时间；气泡 surface 底 + border。
- 用户消息：右对齐 primary 底白字气泡。
- 系统消息：居中弱化行（短横线 + 图标 + 文案）替代现在的黄色气泡。
- 裁判总结：warning 色系卡片 + `scale` 图标 + 「裁判总结 · 第 x 轮」 + `VERDICT` 徽标（轮数从消息计数推导，推不出则不带轮次）。
- Markdown 样式适配新 tokens；代码块保持固定深色。

### CreateMeetingDialog（双栏）
- 左栏：会议主题 Input + 三种模式选择卡片（radio、选中 primary 描边；每张卡片带模式说明 + Agent 链路 mono 小字预览）。
- 右栏（选辩论时）：辩论轮数 Slider（1–3）、正方/反方人格 Select、**允许观众质询 Switch**、自动连播 Switch；选圆桌时只显示轮数 Slider（1–10）+ 自动连播。
- 底部：取消 + 「创建并进入会议」（mono 计划摘要小字）。

### ChatInput
- 大圆角（XL 28）输入框 + placeholder 提示 + 右侧圆形发送按钮（primary，GLOW）。
- 下方 mono 小字：Enter 发送 · Shift+Enter 换行。

## 后端改动（唯一，additive）

`inquiry_enabled` 字段贯通：
- `Meeting` 模型 + `CreateMeetingRequest` 加 `inquiry_enabled: bool = True`（默认 True = 现行为）。
- `db.py`：`meetings` 表幂等补列 `inquiry_enabled INTEGER DEFAULT 1`（照 `auto_play` 迁移模式），`save_meeting`/`get_meeting` 读写。
- `main.create_meeting` 透传。
- `turns`/`main._run_debate_step`：`inquiry = _pending_inquiry(meeting)` 后增加 `if inquiry and meeting.inquiry_enabled and spec["kind"] != "judge"` 门控。
- 兼容性：`test_web.py` 与现有 pytest 不发该字段 → 默认 True → 行为不变。

## 不变的部分

- API 端点与 SSE 事件协议（新增字段仅为请求侧可选 + Meeting dump 多一个键）。
- hooks 状态机、`lib/api.ts`、`lib/sse.ts`、`/?meeting=` 直开、FastAPI 托管 dist、Docker 多阶段。
- 路由/状态管理不引入新库。

## 错误处理

- 沿用现有 toast 体系；无新增错误路径（延迟测量失败显示 `—`）。

## 测试与验收

- 现有验证链全绿：`npm run build`/`lint`、`ruff`、pytest（web 相关）、`test_web.py`、Docker 构建。
- Playwright 无头截图对照 Figma：首页、创建弹窗（辩论态）、会议室（暗/亮）三态，控制器目视比对。
- 手工冒烟：三模式创建、步进/连播、插话、删除、`?meeting=` 直开、主题切换、窗口 <lg 时右栏隐藏。

## 明确不做（YAGNI）

- 不放假/装饰性数据。
- 不引入图表库、动效库（framer-motion 等）、新状态库。
- 不做响应式移动端专门设计（仅保证 <lg 隐藏右栏、侧边栏保留）。
- 不做多语言。
