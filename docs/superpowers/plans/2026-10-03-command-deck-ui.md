# 「夜间指挥舱」UI 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 Figma 设计稿（6 画板）把前端重构为「夜间指挥舱」风格：新 Tokens、布局重构（右栏遥测、双栏创建弹窗、仪式感步进条），后端加 `inquiry_enabled` 字段做真观众质询开关。

**Architecture:** 重写 `index.css` 语义 Tokens（暗默认/亮可选）；纯展示层组件全部换皮 + 3 个新组件（Eyebrow、RightRail、HeroHome 改造）；新增 `src/lib/sequence.ts` 移植后端 `build_sequence` 推导真实轮次进度；`useMeetingRoom` 增加 SSE 延迟实测；后端唯一改动为 `inquiry_enabled` 字段贯通（照 `auto_play` 迁移模式）。

**Tech Stack:** 既有 Vite + React + TS + Tailwind v4 + shadcn/ui；无新依赖。视觉标准 = Figma 文件（控制器持有一手 design context，可在实施时按组件拉取）。

**设计文档:** `docs/superpowers/specs/2026-10-03-command-deck-ui-design.md`

## Global Constraints

- 不展示任何假数据：右栏仅显示真实可算项；推导不出的项不渲染。
- 后端 API/SSE 协议 additive-only；除 `inquiry_enabled` 外不得改后端。
- 默认主题 = 暗色；保留亮色 + 跟随系统 + 手动切换（`a2a-theme` localStorage 键不变）。
- 全中文界面；技术眉题/标签用 JetBrains Mono 大写英文短词（如 `NEXT SPEAKER`、`SESSION TELEMETRY`，设计稿如此）。
- 颜色精确值（暗色）：bg `#070A12`、surface `#0E1423`、raised `#151C2E`、border `#263049`、text `#F2F5FF`/`#A8B1C7`/`#69748D`、primary `#745CFF`、cyan `#32D6E8`、success `#35D07F`、judge `#F6B84A`、danger `#FF6680`；亮色：bg `#F1F3F9`、surface `#FFFFFF`、text `#15192A`。
- GLOW 阴影 `0 0 18px rgba(116,92,255,0.33)`；SOFT `0 10px 30px rgba(17,22,42,0.08)`；圆角 6/10/14/20/28。
- 每个 Task 结束 `npm run build` + `npm run lint`（frontend workdir）通过后 commit；后端触碰的 Task 另跑 `uv run ruff check .`。
- 环境：Windows PowerShell；后端长验证（test_web/docker）由控制器在 Task 8 统一执行，子代理不做长验证。

## File Structure

```
web/frontend/src/
├── index.css                    # 重写：Tokens + 字体 + 网格纹理 + markdown/思考点
├── lib/sequence.ts              # 新增：buildSequence/buildProgress（移植 turns.py）
├── hooks/useMeetingRoom.ts      # 改：+sseLatencyMs
├── components/
│   ├── Eyebrow.tsx              # 新增：mono 青色眉题
│   ├── Sidebar.tsx              # 重绘
│   ├── HeroHome.tsx             # 改自 HomeEmptyState（重命名）
│   ├── RoomHeader.tsx           # 重绘（+会话编号）
│   ├── ParticipantBar.tsx       # 重绘（胶囊）
│   ├── TurnControlBar.tsx       # 重绘（⚡+眉题+轮次）
│   ├── RightRail.tsx            # 新增：轮次进度 + TELEMETRY
│   ├── MessageBubble.tsx        # 重绘（角色标签/系统分隔线/裁判卡）
│   ├── MarkdownContent.tsx      # 小改（代码块配色对齐 Tokens）
│   ├── ChatInput.tsx            # 重绘（XL 圆角+圆形发送）
│   └── CreateMeetingDialog.tsx  # 双栏重构 + 质询开关
├── App.tsx                      # 会议室布局接入 RightRail；HomeEmptyState→HeroHome
web/main.py                      # inquiry_enabled 贯通（模型/请求/创建/质询门控）
web/db.py                        # 幂等补列 inquiry_enabled
web/turns.py                     # 不动
```

---

### Task 1: Tokens、字体、网格纹理

**Files:** Modify `web/frontend/index.html`、`web/frontend/src/index.css`、`web/frontend/src/hooks/useTheme.ts`

**Interfaces:**
- Produces: shadcn 语义 CSS 变量新值（暗/亮两套）；`.bg-grid` 工具类；`--font-sans`/`--font-mono`；`useTheme` 默认 `"dark"`。

- [ ] **Step 1: index.html 加字体**

在 `<head>` 内、其它 script 之前加入：

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link
  href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;700&display=swap"
  rel="stylesheet"
/>
```

（Google Fonts 不可达时的回退栈已含系统字体；离线开发不阻塞。）

- [ ] **Step 2: 重写 src/index.css 的 Tokens**

保留文件顶部 imports 与 `@theme inline` 结构、`.thinking-dot`/`.markdown-body` 两个追加块，替换其中的 `:root` 与 `.dark` 变量块为（Tailwind v4 OKLCH 变量改用 hex 即可，Tailwind v4 接受任意颜色格式）：

```css
:root {
  --radius: 14px;
  --background: #f1f3f9;
  --foreground: #15192a;
  --card: #ffffff;
  --card-foreground: #15192a;
  --popover: #ffffff;
  --popover-foreground: #15192a;
  --primary: #745cff;
  --primary-foreground: #ffffff;
  --secondary: #e8ebf4;
  --secondary-foreground: #15192a;
  --muted: #e8ebf4;
  --muted-foreground: #8891a5;
  --accent: #e9e6ff;
  --accent-foreground: #4c3ad6;
  --destructive: #ff6680;
  --border: #e2e6f0;
  --input: #e2e6f0;
  --ring: #745cff;
  --chart-1: #745cff;
  --chart-2: #32d6e8;
  --chart-3: #35d07f;
  --chart-4: #f6b84a;
  --chart-5: #ff6680;
  --sidebar: #ffffff;
  --sidebar-foreground: #15192a;
  --sidebar-primary: #745cff;
  --sidebar-primary-foreground: #ffffff;
  --sidebar-accent: #e9e6ff;
  --sidebar-accent-foreground: #4c3ad6;
  --sidebar-border: #e2e6f0;
  --sidebar-ring: #745cff;
  --assist: #0ea5b5;
}

.dark {
  --background: #070a12;
  --foreground: #f2f5ff;
  --card: #0e1423;
  --card-foreground: #f2f5ff;
  --popover: #0e1423;
  --popover-foreground: #f2f5ff;
  --primary: #745cff;
  --primary-foreground: #ffffff;
  --secondary: #151c2e;
  --secondary-foreground: #f2f5ff;
  --muted: #151c2e;
  --muted-foreground: #69748d;
  --accent: #1c2140;
  --accent-foreground: #e9e6ff;
  --destructive: #ff6680;
  --border: #263049;
  --input: #263049;
  --ring: #745cff;
  --chart-1: #745cff;
  --chart-2: #32d6e8;
  --chart-3: #35d07f;
  --chart-4: #f6b84a;
  --chart-5: #ff6680;
  --sidebar: #0e1423;
  --sidebar-foreground: #f2f5ff;
  --sidebar-primary: #745cff;
  --sidebar-primary-foreground: #ffffff;
  --sidebar-accent: #1c2140;
  --sidebar-accent-foreground: #e9e6ff;
  --sidebar-border: #263049;
  --sidebar-ring: #745cff;
  --assist: #32d6e8;
}
```

`@theme inline` 中补映射（沿用既有写法追加）：

```css
--font-sans: "Inter", "HarmonyOS Sans SC", "PingFang SC", "Microsoft YaHei", ui-sans-serif, system-ui, sans-serif;
--font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
--color-assist: var(--assist);
```

文件末尾追加（网格纹理 + mono 标签工具类 + 代码块配色）：

```css
.bg-grid {
  background-image:
    repeating-linear-gradient(to right, var(--border) 0 1px, transparent 1px 80px),
    repeating-linear-gradient(to bottom, var(--border) 0 1px, transparent 1px 80px);
}
.dark .bg-grid { opacity: 0.18; }
.light-safe .bg-grid { opacity: 0.5; }

.text-assist { color: var(--assist); }
.shadow-glow { box-shadow: 0 0 18px rgba(116, 92, 255, 0.33); }
.shadow-soft { box-shadow: 0 10px 30px rgba(17, 22, 42, 0.08); }
```

- [ ] **Step 3: useTheme 默认暗色**

`src/hooks/useTheme.ts` 初始值 `localStorage.getItem(STORAGE_KEY) as Theme) || "system"` 改为 `|| "dark"`。

- [ ] **Step 4: 验证**：`npm run build` + `npm run lint`（workdir `web/frontend`）通过；现有界面应已整体变为新配色（组件用语义 token，自动换肤）。
- [ ] **Step 5: Commit** `feat(web): command-deck design tokens, fonts and grid texture`

---

### Task 2: sequence.ts（真实轮次推导）

**Files:** Create `web/frontend/src/lib/sequence.ts`

**Interfaces:**
- Consumes: `@/types` 的 `Meeting`/`MeetingMode`。
- Produces（Task 6 RightRail / TurnControlBar 依赖）:

```ts
export type SlotState = "done" | "current" | "pending"
export interface SlotView {
  kind: "agent" | "debate" | "judge" | "fallback"
  key: string            // 原始 key（agent key / pro|con|judge）
  participantId: string  // 映射后的参与者 id
  index: number
  state: SlotState
}
export interface ProgressView {
  slots: SlotView[]
  round: { current: number; total: number } | null  // pipeline 为 null
}
export function buildSequence(mode: MeetingMode, maxRounds: number): { kind: string; key: string; index: number }[]
export function buildProgress(meeting: Meeting): ProgressView
```

- [ ] **Step 1: 写 src/lib/sequence.ts**（逐行移植 `web/turns.py` 的 `build_sequence`，槽位→参与者映射照 `main._participant_preview`：agent/fallback key=参与者 id；debate pro→`meeting.pro_persona`、con→`meeting.con_persona`；judge→`"judge"`；`seqIndex = meeting.turn_state?.seq_index ?? 0`；`state: index < seqIndex ? done : index === seqIndex ? current : pending`。轮数：pipeline → null；roundtable → agent 槽 `clamp(floor((index-1)/5)+1, 1, N)`、首尾 moderator 槽不算轮；debate → debate 槽 `min(floor(index/2)+1, N)`、judge 槽为最终总结（round = N）。）

- [ ] **Step 2: 验证** build + lint 通过（本 Task 纯函数，行为验证并入 Task 8 截图/冒烟）。
- [ ] **Step 3: Commit** `feat(web): port turn sequence for real round progress`

---

### Task 3: useMeetingRoom 增加 SSE 延迟实测

**Files:** Modify `web/frontend/src/hooks/useMeetingRoom.ts`

**Interfaces:**
- Produces: hook 返回值新增 `sseLatencyMs: number | null`（每次 connect 到 init 的毫秒数，重连后更新；断开置 null）。

- [ ] **Step 1:** connect() 内 `const t0 = performance.now()`；init 回调里 `setSseLatencyMs(Math.round(performance.now() - t0))`；onerror 置 null；cleanup 重置；返回对象加该字段（`useState<number | null>(null)`）。
- [ ] **Step 2:** build + lint；Commit `feat(web): measure sse round-trip latency`

---

### Task 4: Sidebar + HeroHome + Eyebrow

**Files:** Create `src/components/Eyebrow.tsx`、`src/components/HeroHome.tsx`；Modify `src/components/Sidebar.tsx`、`src/components/HomeEmptyState.tsx`（删除）、`src/App.tsx`（import 改名）

**Interfaces:**
- Produces: `<Eyebrow>{string}</Eyebrow>`（`font-mono text-[10px] tracking-[0.08em] uppercase text-assist`）；`<HeroHome onCreate={() => void} />`（props 同 HomeEmptyState）。

- [ ] **Step 1:** Eyebrow 组件（一行）。
- [ ] **Step 2:** HeroHome：居中卡片按设计稿重绘——青色 Eyebrow「INITIALIZE MULTI-AGENT SESSION」、Display 标题两行、副标题、主按钮「发起第一次会议」、下方 `01 顺序编排 / 02 实时插话 / 03 自动总结` 三列 mono 编号特性行。视觉细节以 Figma「空状态首页」画板为准（控制器可拉 design context）。
- [ ] **Step 3:** Sidebar 重绘：品牌区（`A²` 方形 primary 渐变标志 + 名称 + mono 标语）、新建会议按钮、`最近会议` Eyebrow + 列表（选中 primary 描边）、底部状态区（真实在线态：`useMeetings` 增加导出 `lastFetchOk: boolean | null`，绿点/红点 + 「服务在线/连接失败」）。
- [ ] **Step 4:** App.tsx 换 import；删除 HomeEmptyState.tsx；主容器加 `bg-grid`（外层 div）。
- [ ] **Step 5:** build + lint；Commit `feat(web): hero home, sidebar and eyebrow in command-deck style`

---

### Task 5: 会议室视图组件重绘

**Files:** Modify `RoomHeader.tsx`、`ParticipantBar.tsx`、`TurnControlBar.tsx`、`MessageBubble.tsx`、`MessageList.tsx`、`ChatInput.tsx`、`MarkdownContent.tsx`（样式与结构，props 契约不变；TurnControlBar 新增可选 props 见下）

**Interfaces:**
- Consumes: Task 2 `buildProgress`（TurnControlBar/MessageBubble 裁判轮次）、Task 3 `sseLatencyMs`（RoomHeader 显示 `· {n}ms`）。
- Produces: `TurnControlBar` props 追加 `progress: ProgressView | null`；`MessageBubble` props 追加 `roleTag?: string`（正方/反方/主持人/AI，由 App 按 meeting.mode + participant id 计算传入）；其余契约不变。

- [ ] **Step 1:** RoomHeader：返回钮 + 主题 H2 + mono `SESSION {id}` + 模式 Badge + 右侧绿点连接状态（含 `· {sseLatencyMs}ms`，null 则不显示）。
- [ ] **Step 2:** ParticipantBar：`AGENTS` Eyebrow + 胶囊（rounded-full raised 底、状态点色：idle=muted、thinking=primary 脉冲、speaking=success）。
- [ ] **Step 3:** TurnControlBar：⚡ 方块（primary 底 GLOW）+ Eyebrow `NEXT SPEAKER · ROUND x/N`（progress.round 为 null 时仅 `NEXT SPEAKER`）+ 发言者 emoji/名字 + Switch + 继续按钮（GLOW）。
- [ ] **Step 4:** MessageBubble：agent 气泡（card 底 + border + 角色标签 + mono 时间）、用户（primary 右对齐）、系统消息改为居中弱化分隔行（`— 文案 —` 样式：短线 + muted 小字）、裁判卡（warning 底 10% + warning 边 + scale 图标 + 「裁判总结 · 第 x 轮」（buildProgress 推导当轮，null 则不带）+ `VERDICT` 徽标）。MessageList 结构不变。
- [ ] **Step 5:** ChatInput：XL 圆角 textarea + 圆形 primary 发送钮 + 下方 mono 提示 `ENTER 发送 · SHIFT+ENTER 换行`。
- [ ] **Step 6:** MarkdownContent：代码块底改 `#05070d`、标题/链接色对齐 tokens；正文样式沿用 `.markdown-body`。
- [ ] **Step 7:** build + lint；Commit `feat(web): command-deck room view components`

---

### Task 6: RightRail + App 布局

**Files:** Create `src/components/RightRail.tsx`；Modify `src/App.tsx`

**Interfaces:**
- Consumes: `buildProgress(meeting)`、`meeting`、`sseLatencyMs`。
- Produces: `<RightRail meeting={Meeting} progress={ProgressView} sseLatencyMs={number | null} />`。

- [ ] **Step 1:** RightRail 两卡片（`rounded-[20px] border bg-card p-[22px]`）：
  - 轮次进度（`ROUND PROGRESS` Eyebrow）：`buildProgress` 槽位列表——done ✓（success）、current（primary 高亮 + 名字）、pending（muted）；`{round.current} / {round.total}` 右上角。round null（pipeline）时该卡片显示各参与方消息计数列表。
  - `SESSION TELEMETRY`：消息数 / 讨论字数（agent 消息 content 长度和）/ 延迟（`{n}ms` 或 `—`）/ 参与方消息数迷你柱状图（div 高度按 max 归一化，chart-1 色）。
- [ ] **Step 2:** App 会议室区改为两列：`flex gap-6`（消息列 `flex-1 min-w-0` + `<aside className="hidden w-[280px] shrink-0 lg:block">` 放 RightRail）；传入 progress/sseLatencyMs；MessageBubble 的 `roleTag` 由 App 计算传入（辩论：pro→`正方`、con→`反方`、judge→`裁判`；圆桌：moderator→`主持`；pipeline/其它：`AI`）。
- [ ] **Step 3:** build + lint；Commit `feat(web): right rail with real round progress and telemetry`

---

### Task 7: 双栏创建弹窗 + 后端 inquiry_enabled

**Files:** Modify `src/components/CreateMeetingDialog.tsx`、`web/main.py`、`web/db.py`

**Interfaces:**
- Consumes: 后端 `/api/meetings` 请求新增可选 `inquiry_enabled: bool = true`；`Meeting` dump 新增该键。
- Produces: `types.ts` 的 `Meeting`/`CreateMeetingBody` 增加 `inquiry_enabled: boolean`。

- [ ] **Step 1: 后端**（照 auto_play 模式）：
  - `db.py` `_migrate` additions 增加 `"inquiry_enabled": "INTEGER DEFAULT 1"`；`save_meeting` 增列读写（`1 if meeting.get("inquiry_enabled", True) else 0`）；`get_meeting` 补 `meeting["inquiry_enabled"] = bool(meeting.get("inquiry_enabled", 1))`。
  - `main.py`：`Meeting`/`CreateMeetingRequest` 加 `inquiry_enabled: bool = True`；`create_meeting(...)` 透传；`_run_debate_step` 质询行改为 `if inquiry and meeting.inquiry_enabled and spec["kind"] != "judge":`。
- [ ] **Step 2:** `ruff check .` + `uv run pytest test_web_turns.py test_web_scheduler.py -q` 通过；`uv run python test_web.py` 通过（不发字段 → 默认 True 行为不变）。
- [ ] **Step 3: 前端**：types.ts 两处加字段；CreateMeetingDialog 双栏（左：主题 Input + 三模式卡片含链路预览 mono 小字；右：`辩论参数` 面板——轮数 Slider、正/反方 Select、允许观众质询 Switch（新 state，默认 true，随 create 提交）、自动连播 Switch；圆桌则右栏仅轮数+自动连播）；底部取消/创建按钮 + mono 摘要。
- [ ] **Step 4:** build + lint；Commit `feat(web+backend): inquiry toggle and two-column create dialog`

---

### Task 8: 端到端验证 + 截图对照（控制器执行）

- [ ] `npm run build`、`npm run lint`、`uv run ruff check .`、pytest 相关、`test_web.py`
- [ ] 起后端 + Playwright 截图：首页、创建弹窗（辩论态）、会议室暗/亮（含右栏），与 Figma 画板目视对照，修正偏差
- [ ] 冒烟：三模式创建/步进/连播/插话/删除/`?meeting=`/主题切换/窄窗口右栏隐藏
- [ ] 修复提交（如有）：`fix(web): command-deck acceptance fixes`
