# 前端重构：Vite + shadcn/ui 设计文档

日期：2026-10-02
状态：已与用户确认

## 背景与目标

当前前端是单文件 `web/static/index.html`（约 557 行）：React 18 UMD + Babel 浏览器内编译 + Tailwind CDN，由 FastAPI 直接托管。视觉陈旧、无类型、无构建、逻辑与视图耦合。

目标：用 shadcn/ui 重做整个前端 UI，顺便优化交互，保持后端 API 与通信协议完全不变。

## 已确认的决策

1. **技术栈**：引入 Node 工具链，`web/frontend/` 下搭建 Vite + React + TypeScript + Tailwind CSS v4 + shadcn/ui（CLI 初始化，组件源码进仓库，放 `src/components/ui/`）。
2. **功能范围**：现有功能 1:1 平移 + 交互优化（见下）。
3. **主题**：shadcn 默认中性色；暗色模式采用 class 策略，跟随系统 + 右上角手动切换。

## 不变的部分（明确约束）

- 后端 API 端点、SSE 事件协议（`init` / `message` / `system` / `status` / `turn_done`）、turn 流式解析逻辑 1:1 保留，仅从前端单文件抽到 `src/hooks/` 与 `src/lib/api.ts`。
- `/?meeting=xxx` 直开会议的行为保留。
- 后端 pytest 测试不动。
- 三种会议模式（pipeline / roundtable / debate）、辩论人格选择、步进/连播、插话、裁判消息等业务行为不变。

## 架构与目录结构

```
web/frontend/
├── index.html
├── package.json
├── vite.config.ts        # @ 别名；dev 代理 /api → http://localhost:8080
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css         # Tailwind v4 + shadcn 主题变量（亮/暗）
│   ├── lib/
│   │   ├── api.ts        # fetch 封装：meetings CRUD、personas、turns
│   │   ├── sse.ts        # SSE + turn 流解析（EventSource / fetch stream）
│   │   └── utils.ts      # cn() 等
│   ├── hooks/
│   │   ├── useMeetings.ts
│   │   ├── useMeetingRoom.ts   # 房间状态机：消息、参与者状态、turn、SSE 重连
│   │   └── useTheme.ts         # 暗色切换（class 策略 + prefers-color-scheme）
│   ├── components/
│   │   ├── ui/           # shadcn 组件（CLI 生成）
│   │   ├── Sidebar.tsx
│   │   ├── CreateMeetingDialog.tsx
│   │   ├── HomeEmptyState.tsx
│   │   ├── RoomHeader.tsx
│   │   ├── ParticipantBar.tsx
│   │   ├── TurnControlBar.tsx
│   │   ├── MessageList.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── MarkdownContent.tsx  # react-markdown + remark-gfm + rehype-highlight + 代码复制
│   │   └── ChatInput.tsx
│   └── types.ts          # Meeting / Message / Participant / Persona / TurnInfo
└── dist/                 # 构建产物（gitignore）
```

- Markdown 渲染：`react-markdown + remark-gfm + rehype-highlight`，替代 marked + DOMPurify + highlight.js（消除 `dangerouslySetInnerHTML` 手工拼接）。
- 全局错误提示：sonner（Toast）。
- 构建产物输出 `web/frontend/dist/`，gitignore；FastAPI 托管该目录。

## 页面与组件设计

### 侧边栏
- 顶部：Logo 标题 + "新建会议" Button → 打开 CreateMeetingDialog。
- 会议列表：可选中卡片（选中态高亮），主题 + 模式/轮数 Badge + 创建时间。
- 删除：卡片 `⋯` DropdownMenu → AlertDialog 确认（替代原生 `confirm()`）。

### 首页（无选中会议）
- 居中 Card 空状态引导（图标 + 标题 + 说明），点击按钮同样打开创建 Dialog。

### 创建会议 Dialog
- Input 主题（非空校验）；RadioGroup 三种模式；roundtable/debate 显示 Slider 轮数（debate 1–3，roundtable 1–10）；debate 显示正方/反方人格两个 Select（数据来自 `/api/personas`）；Switch 自动连播。
- 提交中 loading 态；成功后关闭 Dialog 并进入房间。

### 会议室
- 顶栏：主题标题 + 模式 Badge（含轮数/步进/自动）+ 连接状态指示（Badge + 呼吸圆点，绿=连接、红=断开）。
- 参与者条：Avatar 卡片一排；thinking 状态显示三点脉冲动画，speaking / idle 文案。
- 步进控制条：显示下一位发言者；"继续" Button 带 Spinner；自动连播/步进用 Switch 切换；turn 进行中禁用。
- 消息流：Avatar + 气泡；用户消息右对齐；系统消息独立样式；裁判总结用特殊边框卡片 + "裁判总结" Badge；Markdown 渲染 + 代码高亮 + 代码块右上角复制按钮。
- 输入区：Textarea 自适应高度，Enter 发送 / Shift+Enter 换行；发送 Button，turn 进行中转 loading。

## 交互优化清单

1. 删除会议：DropdownMenu + AlertDialog 确认。
2. sonner Toast：创建/删除/发送失败、SSE 断连提示；SSE 断开后指数退避自动重连，成功后 toast。
3. 创建表单校验 + 提交 loading。
4. 消息流智能滚动：用户向上滚动时暂停自动滚动，显示"↓ 回到底部"悬浮按钮。
5. Textarea 自适应高度；Enter / Shift+Enter。
6. 步进按钮 loading 态。
7. 代码块复制按钮；长消息不撑破气泡（内容区滚动）。
8. 空状态设计（侧边栏无会议、首页）。
9. 暗色模式下代码高亮主题跟随切换。

## 构建与部署

- 开发：`cd web/frontend && npm i && npm run dev`（Vite 代理 `/api` 到本地 FastAPI）。
- 构建：`npm run build` → `dist/`。
- FastAPI：`serve_react()` 改为返回 `dist/index.html`；挂载 `dist/assets`；删除 `web/static/`。
- `web/Dockerfile` 多阶段：`node:20-slim` 安装依赖并构建 → 产物拷入 Python 运行镜像。
- README 增加前端开发/构建说明。

## 错误处理

- 所有 fetch 失败走 toast，不弹原生 alert。
- SSE `onerror` 关闭后由重连逻辑接管，房间状态标记为断开。
- turn 流读取中断（网络异常）时结束 loading 并 toast。

## 测试与验收

- 后端 pytest 不动；本项目原本无前端测试，不新增测试框架（YAGNI），前端加 ESLint（Vite 模板自带）。
- 手工验收清单：
  1. 三种模式各创建一个会议；
  2. 圆桌/辩论：步进推进、自动连播、中途插话；
  3. 辩论裁判总结消息样式正确；
  4. 删除会议（AlertDialog）；
  5. 暗色/亮色切换 + 跟随系统；
  6. `/?meeting=xxx` 直开；
  7. 断网 → SSE 断连提示 → 恢复后自动重连；
  8. `npm run build` 产物由 FastAPI 正常托管；
  9. `docker compose build web` 跑通并可访问。

## 明确不做（YAGNI）

- 不引入前端测试框架、状态管理库（Redux 等）、路由库（单页两视图用 state 切换即可）、next-themes（自带轻量 useTheme 即可）。
- 不改后端任何 API/协议。
- 不做多语言（保持中文 UI）。
