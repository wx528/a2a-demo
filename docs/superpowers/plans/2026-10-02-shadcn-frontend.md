# shadcn/ui 前端重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Vite + React + TypeScript + Tailwind v4 + shadcn/ui 重写 `web/static/index.html` 前端，功能 1:1 平移并优化交互，后端 API/SSE 协议不变。

**Architecture:** 前端独立工程 `web/frontend/`，构建产物 `dist/` 由 FastAPI 托管；状态逻辑抽为 hooks，SSE/turn 流解析抽为 lib；Docker 多阶段构建（node 构建 → Python 运行）。

**Tech Stack:** Vite 6、React（模板默认版本）、TypeScript、Tailwind CSS v4（@tailwindcss/vite）、shadcn/ui（neutral 基色）、react-markdown + remark-gfm + rehype-highlight + highlight.js、lucide-react、sonner。

**设计文档:** `docs/superpowers/specs/2026-10-02-shadcn-frontend-design.md`

## Global Constraints

- 所有 UI 文案为中文。
- 后端 API 端点与 SSE 协议（`init`/`message`/`system`/`status`/`turn_done`）**不得改动**；只改 `web/main.py` 的静态托管部分。
- `GET /` 在 dist 未构建时必须返回 **200**（占位页），因为 `test_web.py:38` 的 `wait_for_ready` 断言 `status_code == 200`，CI 无 Node 构建步骤。
- `/?meeting=xxx` 直开会议行为保留。
- 主题：shadcn neutral 基色；暗色用 class 策略（`documentElement.classList.toggle("dark")`）；代码块固定深色（`github-dark` 主题，不随主题切换）。
- Docker 中 Node 构建用 `node:20-slim`。
- 不引入前端测试框架、状态管理库、路由库、next-themes。
- 每个 Task 结束必须 `npm run build`（含 tsc 类型检查）与 `npm run lint` 通过后 commit。
- 命令环境为 Windows PowerShell；npm 命令在 `web/frontend` 下执行（用 workdir 参数）。

## File Structure（最终形态）

```
web/frontend/                  # 新 Vite 工程（模板文件不一一列出）
├── index.html                 # 改 lang/title
├── vite.config.ts             # 改：@ 别名 + /api 代理
├── tsconfig.app.json          # 改：paths
├── src/
│   ├── main.tsx               # 改：Toaster
│   ├── App.tsx                # 重写
│   ├── index.css              # 改：+ hljs 导入/markdown/思考点样式
│   ├── types.ts
│   ├── lib/{api,sse,labels}.ts        # utils.ts 由 shadcn 生成
│   ├── hooks/{useTheme,useMeetings,useMeetingRoom}.ts
│   ├── components/
│   │   ├── ui/*                       # shadcn CLI 生成
│   │   ├── ThemeToggle.tsx
│   │   ├── Sidebar.tsx
│   │   ├── CreateMeetingDialog.tsx
│   │   ├── HomeEmptyState.tsx
│   │   ├── RoomHeader.tsx
│   │   ├── ParticipantBar.tsx
│   │   ├── TurnControlBar.tsx
│   │   ├── MessageList.tsx
│   │   ├── MessageBubble.tsx
│   │   ├── MarkdownContent.tsx
│   │   └── ChatInput.tsx
│   └── (dist/ gitignore，由 Vite 模板自带)
web/main.py                    # 改：serve_react + assets 挂载（约 544-549 行）
web/static/                    # 删除
web/Dockerfile                 # 重写为多阶段
README.md                      # 增前端说明
```

---

### Task 1: 脚手架 Vite + React + TS + Tailwind v4 + shadcn/ui

**Files:**
- Create: `web/frontend/**`（脚手架生成）
- Modify: `web/frontend/vite.config.ts`、`web/frontend/tsconfig.app.json`、`web/frontend/index.html`

**Interfaces:**
- Produces: 可构建的 Vite 工程；`@/*` 路径别名；dev 代理 `/api → http://localhost:8080`；`src/components/ui/*` 下 shadcn 组件；`src/lib/utils.ts` 的 `cn()`。后续所有 Task 依赖这些。

- [ ] **Step 1: 创建 Vite 工程并安装依赖**

```powershell
npm create vite@latest frontend -- --template react-ts
npm install
npm install tailwindcss @tailwindcss/vite
npm install react-markdown remark-gfm rehype-highlight highlight.js lucide-react sonner
```

（workdir=`web`；后两条 npm install 的 workdir=`web/frontend`）

- [ ] **Step 2: 初始化 shadcn 并添加组件**

```powershell
npx shadcn@latest init -y -d -b neutral
npx shadcn@latest add -y button input textarea label select slider switch badge card dialog alert-dialog dropdown-menu avatar scroll-area separator tooltip radio-group
```

（workdir=`web/frontend`。init 会自动改写 `src/index.css`（写入 Tailwind v4 + neutral 主题变量 + `@custom-variant dark`）、`tsconfig.json`/`tsconfig.app.json`（paths）和 `vite.config.ts`（alias）。）

- [ ] **Step 3: 核对 vite.config.ts**

init 后打开 `web/frontend/vite.config.ts`，确认/补齐为以下内容（保留 init 写入的 alias，追加 proxy 与端口）：

```ts
import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8080", changeOrigin: true },
    },
  },
})
```

注：若 init 生成的 alias 写法是 `fileURLToPath(new URL(...))`，保留其写法亦可，只需保证 `@` → `./src`。

- [ ] **Step 4: 核对 tsconfig.app.json 的 paths**

`compilerOptions` 中应存在（没有则补上）：

```json
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```

- [ ] **Step 5: 修改 index.html**

`web/frontend/index.html` 的 `<html lang="en">` 改为 `lang="zh-CN"`，`<title>` 改为 `A2A 多人会议室`。

- [ ] **Step 6: 构建与 lint 验证**

```powershell
npm run build
npm run lint
```

Expected: `npm run build` 输出 `dist/`（vite build 完成，tsc 无错误）；lint 无 error。

- [ ] **Step 7: Commit**

```powershell
git add web/frontend
git commit -m "feat(web): scaffold Vite + React + Tailwind v4 + shadcn/ui frontend"
```

（Vite 模板自带的 `web/frontend/.gitignore` 已覆盖 `node_modules/` 与 `dist/`，确认 `git status` 中未出现二者。）

---

### Task 2: 主题系统 + 全局样式 + Toaster

**Files:**
- Create: `web/frontend/src/hooks/useTheme.ts`、`web/frontend/src/components/ThemeToggle.tsx`
- Modify: `web/frontend/src/index.css`、`web/frontend/src/main.tsx`

**Interfaces:**
- Produces: `useTheme(): { theme: "light" | "dark" | "system"; setTheme(t): void }`；`<ThemeToggle />` 组件（Task 7 的 Sidebar 使用）；全局 `.markdown-body` 样式类与 `.thinking-dot` 动画（Task 5/6 使用）；sonner `<Toaster />` 全局挂载（所有 Task 的 `toast.*` 依赖它）。

- [ ] **Step 1: 写 src/hooks/useTheme.ts**

```ts
import { useCallback, useEffect, useState } from "react"

type Theme = "light" | "dark" | "system"

const STORAGE_KEY = "a2a-theme"

function applyTheme(theme: Theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches)
  document.documentElement.classList.toggle("dark", dark)
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem(STORAGE_KEY) as Theme) || "system",
  )

  useEffect(() => {
    applyTheme(theme)
    const media = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      if (theme === "system") applyTheme("system")
    }
    media.addEventListener("change", onChange)
    return () => media.removeEventListener("change", onChange)
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next)
    setThemeState(next)
  }, [])

  return { theme, setTheme }
}
```

- [ ] **Step 2: 写 src/components/ThemeToggle.tsx**

```tsx
import { Monitor, Moon, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useTheme } from "@/hooks/useTheme"

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8" title="切换主题">
          {theme === "dark" ? <Moon className="h-4 w-4" /> : theme === "light" ? <Sun className="h-4 w-4" /> : <Monitor className="h-4 w-4" />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <Sun />亮色
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <Moon />暗色
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <Monitor />跟随系统
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
```

- [ ] **Step 3: 修改 src/index.css**

CSS `@import` 必须位于文件顶部其它规则之前。在文件最上方 `@import "tailwindcss";`（init 生成）的**紧后面**插入一行：

```css
@import "highlight.js/styles/github-dark.min.css";
```

在文件**末尾**追加（init 生成的 `:root`/`.dark` 主题变量块保持不动）：

```css
/* 思考中三点动画 */
.thinking-dot {
  animation: bounce-dot 1.4s infinite ease-in-out both;
}
.thinking-dot:nth-child(1) { animation-delay: -0.32s; }
.thinking-dot:nth-child(2) { animation-delay: -0.16s; }
@keyframes bounce-dot {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* Markdown 排版（agent 消息气泡内） */
.markdown-body { line-height: 1.7; font-size: 0.875rem; }
.markdown-body h1 { font-size: 1.25rem; font-weight: 700; margin: 1rem 0 0.5rem; }
.markdown-body h2 { font-size: 1.125rem; font-weight: 700; margin: 0.875rem 0 0.5rem; }
.markdown-body h3 { font-size: 1rem; font-weight: 600; margin: 0.75rem 0 0.5rem; }
.markdown-body p { margin: 0.5rem 0; }
.markdown-body ul { list-style-type: disc; padding-left: 1.5rem; margin: 0.5rem 0; }
.markdown-body ol { list-style-type: decimal; padding-left: 1.5rem; margin: 0.5rem 0; }
.markdown-body blockquote {
  border-left: 3px solid var(--border);
  padding-left: 0.75rem;
  color: var(--muted-foreground);
  margin: 0.5rem 0;
}
.markdown-body code:not(pre code) {
  background: var(--muted);
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  font-size: 0.8125rem;
}
.markdown-body pre code { background: transparent; padding: 0; }
.markdown-body pre .hljs { background: transparent; padding: 0; }
.markdown-body hr { border-color: var(--border); margin: 1rem 0; }
```

- [ ] **Step 4: 修改 src/main.tsx（挂载 Toaster）**

```tsx
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { Toaster } from "sonner"
import App from "./App"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    <Toaster position="top-center" richColors />
  </StrictMode>,
)
```

- [ ] **Step 5: 构建验证**

```powershell
npm run build
npm run lint
```

Expected: 均通过（`github-dark.min.css` 存在于 highlight.js 包内）。

- [ ] **Step 6: Commit**

```powershell
git add web/frontend/src
git commit -m "feat(web): theme system, global markdown styles and toaster"
```

---

### Task 3: 类型定义 + API 客户端 + SSE 解析器 + 文案工具

**Files:**
- Create: `web/frontend/src/types.ts`、`web/frontend/src/lib/api.ts`、`web/frontend/src/lib/sse.ts`、`web/frontend/src/lib/labels.ts`

**Interfaces:**
- Produces（后续 Task 全部依赖，命名必须一致）:
  - `types.ts`: `MeetingMode`、`Participant`、`ChatMessage`、`Meeting`、`MeetingSummary`、`Persona`、`TurnInfo`
  - `api.ts`: `api.listMeetings(): Promise<MeetingSummary[]>`、`api.getMeeting(id): Promise<Meeting>`、`api.deleteMeeting(id): Promise<{deleted:boolean}>`、`api.createMeeting(body): Promise<Meeting>`、`api.listPersonas(): Promise<Persona[]>`、`api.sendMessage(meetingId, content): Promise<ChatMessage>`、`api.peekNextTurn(meetingId): Promise<TurnInfo>`
  - `sse.ts`: `createSseParser(onBlock: (b: {event: string; data: string}) => void): { push(chunk: string): void }`
  - `labels.ts`: `modeBadgeText(mode, maxRounds): string`、`modeBadgeTextFull(meeting): string`

- [ ] **Step 1: 写 src/types.ts**

字段与 `web/main.py` 的 Pydantic 模型（Participant/ChatMessage/Meeting）、`db.list_meetings()` 返回列、`/api/personas`、`/next-turn` 响应一一对应：

```ts
export type MeetingMode = "pipeline" | "roundtable" | "debate"

export interface Participant {
  id: string
  name: string
  role: string
  avatar: string
  status: "idle" | "thinking" | "speaking"
}

export interface ChatMessage {
  id: string
  meeting_id: string
  participant_id: string
  participant_name: string
  role: string
  content: string
  timestamp: string
  type: string // message | system | pass | judge | status
}

export interface Meeting {
  id: string
  topic: string
  mode: MeetingMode
  max_rounds: number
  auto_play: boolean
  pro_persona: string
  con_persona: string
  created_at: string
  participants: Participant[]
  messages: ChatMessage[]
  status: string
}

export interface MeetingSummary {
  id: string
  topic: string
  mode: MeetingMode
  max_rounds: number
  created_at: string
  status: string
  auto_play: boolean
}

export interface Persona {
  id: string
  name: string
  style: string
  avatar: string
}

export interface TurnInfo {
  done: boolean
  next: { participant_id: string; name: string; avatar: string } | null
  mode?: MeetingMode
  auto_play?: boolean
}
```

- [ ] **Step 2: 写 src/lib/api.ts**

```ts
import type {
  ChatMessage,
  Meeting,
  MeetingMode,
  MeetingSummary,
  Persona,
  TurnInfo,
} from "@/types"

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init)
  if (!res.ok) throw new Error(`请求失败：${res.status}`)
  return res.json() as Promise<T>
}

export interface CreateMeetingBody {
  topic: string
  mode: MeetingMode
  max_rounds: number
  auto_play: boolean
  pro_persona: string
  con_persona: string
}

export const api = {
  listMeetings: () => request<MeetingSummary[]>("/api/meetings"),

  getMeeting: (id: string) => request<Meeting>(`/api/meetings/${id}`),

  deleteMeeting: (id: string) =>
    request<{ deleted: boolean }>(`/api/meetings/${id}`, { method: "DELETE" }),

  createMeeting: (body: CreateMeetingBody) =>
    request<Meeting>("/api/meetings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  listPersonas: () => request<Persona[]>("/api/personas"),

  sendMessage: (meetingId: string, content: string) =>
    request<ChatMessage>(`/api/meetings/${meetingId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }),

  peekNextTurn: (meetingId: string) =>
    request<TurnInfo>(`/api/meetings/${meetingId}/next-turn`),
}
```

- [ ] **Step 3: 写 src/lib/sse.ts**

从旧 `index.html` 的 `runNextTurn` 流解析逻辑（原 209-224 行）移植：

```ts
export interface SseBlock {
  event: string
  data: string
}

export function createSseParser(onBlock: (block: SseBlock) => void) {
  let buf = ""
  return {
    push(chunk: string) {
      buf += chunk
      let idx: number
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        let event = "message"
        const dataLines: string[] = []
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) event = line.slice(7)
          else if (line.startsWith("data: ")) dataLines.push(line.slice(6))
        }
        if (dataLines.length > 0) onBlock({ event, data: dataLines.join("\n") })
      }
    },
  }
}
```

- [ ] **Step 4: 写 src/lib/labels.ts**

```ts
import type { Meeting, MeetingMode } from "@/types"

export function modeBadgeText(mode: MeetingMode, maxRounds: number): string {
  if (mode === "roundtable") return `圆桌 · ${maxRounds}轮`
  if (mode === "debate") return `辩论 · ${maxRounds}轮`
  return "流水线"
}

export function modeBadgeTextFull(meeting: Pick<Meeting, "mode" | "max_rounds" | "auto_play">): string {
  if (meeting.mode === "roundtable") return `圆桌讨论 · ${meeting.max_rounds} 轮`
  if (meeting.mode === "debate") {
    return `辩论 · ${meeting.max_rounds} 轮 · ${meeting.auto_play ? "自动" : "步进"}`
  }
  return "流水线"
}
```

- [ ] **Step 5: 构建验证**

```powershell
npm run build
npm run lint
```

Expected: 通过（无未使用导出报错；lint 若对 `labels.ts` 无引用报 unused，属正常，Vite 模板 ESLint 默认不查未使用导出）。

- [ ] **Step 6: Commit**

```powershell
git add web/frontend/src
git commit -m "feat(web): types, api client, sse parser and labels"
```

---

### Task 4: Hooks（useMeetings + useMeetingRoom）

**Files:**
- Create: `web/frontend/src/hooks/useMeetings.ts`、`web/frontend/src/hooks/useMeetingRoom.ts`

**Interfaces:**
- Consumes: Task 3 的 `api`/`createSseParser`/类型；Task 2 的全局 Toaster（`toast` 来自 `sonner` 包）。
- Produces:
  - `useMeetings(): { meetings: MeetingSummary[]; refresh(): Promise<void>; remove(id): Promise<boolean> }`
  - `useMeetingRoom(meetingId: string | null): { meeting: Meeting | null; connected: boolean; turnInfo: TurnInfo | null; turnRunning: boolean; autoPlay: boolean; setAutoPlay(v: boolean): void; runNextTurn(): Promise<void>; sendMessage(content): Promise<boolean> }`

- [ ] **Step 1: 写 src/hooks/useMeetings.ts**

```ts
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { MeetingSummary } from "@/types"

export function useMeetings() {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])

  const refresh = useCallback(async () => {
    try {
      setMeetings(await api.listMeetings())
    } catch {
      toast.error("加载会议列表失败")
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const remove = useCallback(async (id: string) => {
    try {
      await api.deleteMeeting(id)
      setMeetings((prev) => prev.filter((m) => m.id !== id))
      toast.success("会议已删除")
      return true
    } catch {
      toast.error("删除会议失败")
      return false
    }
  }, [])

  return { meetings, refresh, remove }
}
```

- [ ] **Step 2: 写 src/hooks/useMeetingRoom.ts**

SSE 连接（指数退避重连）、turn 流执行、状态机。自递归通过 `runNextTurnRef` 解决（useCallback 不能引用自身）：

```ts
import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { createSseParser } from "@/lib/sse"
import type { ChatMessage, Meeting, Participant, TurnInfo } from "@/types"

export function useMeetingRoom(meetingId: string | null) {
  const [meeting, setMeeting] = useState<Meeting | null>(null)
  const [connected, setConnected] = useState(false)
  const [turnInfo, setTurnInfo] = useState<TurnInfo | null>(null)
  const [turnRunning, setTurnRunning] = useState(false)
  const [autoPlay, setAutoPlayState] = useState(false)

  const autoPlayRef = useRef(false)
  const runningRef = useRef(false)
  const retryRef = useRef(0)
  const reconnectTimer = useRef<number | null>(null)
  const evtSourceRef = useRef<EventSource | null>(null)
  const runNextTurnRef = useRef<() => Promise<void>>(async () => {})

  const setAutoPlay = useCallback((value: boolean) => {
    autoPlayRef.current = value
    setAutoPlayState(value)
  }, [])

  // SSE：init 快照 + 断线指数退避重连
  useEffect(() => {
    if (!meetingId) return
    let disposed = false

    const connect = () => {
      const es = new EventSource(`/api/meetings/${meetingId}/events`)
      evtSourceRef.current = es
      es.addEventListener("init", (e) => {
        if (disposed) return
        const wasReconnect = retryRef.current > 0
        const data = JSON.parse((e as MessageEvent).data) as Meeting
        setMeeting(data)
        setConnected(true)
        setAutoPlay(data.auto_play)
        retryRef.current = 0
        api.peekNextTurn(meetingId).then(setTurnInfo).catch(() => {})
        if (wasReconnect) toast.success("已恢复实时连接")
      })
      es.onerror = () => {
        if (disposed) return
        setConnected(false)
        es.close()
        const delay = Math.min(15000, 1000 * 2 ** retryRef.current)
        retryRef.current += 1
        if (retryRef.current === 1) toast.error("实时连接已断开，正在重连…")
        reconnectTimer.current = window.setTimeout(connect, delay)
      }
    }
    connect()

    return () => {
      disposed = true
      evtSourceRef.current?.close()
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current)
      setConnected(false)
      setMeeting(null)
      setTurnInfo(null)
      retryRef.current = 0
    }
  }, [meetingId, setAutoPlay])

  const applyTurnEvent = useCallback(
    (event: string, data: string) => {
      if (event === "message") {
        const msg = JSON.parse(data) as ChatMessage
        setMeeting((prev) => (prev ? { ...prev, messages: [...prev.messages, msg] } : prev))
      } else if (event === "system") {
        const { content } = JSON.parse(data) as { content: string }
        const msg: ChatMessage = {
          id: `sys-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          meeting_id: meetingId ?? "",
          participant_id: "system",
          participant_name: "系统",
          role: "system",
          content,
          timestamp: new Date().toLocaleTimeString(),
          type: "system",
        }
        setMeeting((prev) => (prev ? { ...prev, messages: [...prev.messages, msg] } : prev))
      } else if (event === "status") {
        const { participant_id, status } = JSON.parse(data) as {
          participant_id: string
          status: string
        }
        setMeeting((prev) =>
          prev
            ? {
                ...prev,
                participants: prev.participants.map((p) =>
                  p.id === participant_id ? { ...p, status: status as Participant["status"] } : p,
                ),
              }
            : prev,
        )
      }
    },
    [meetingId],
  )

  const runNextTurn = useCallback(async () => {
    if (!meetingId || runningRef.current) return
    runningRef.current = true
    setTurnRunning(true)
    try {
      const res = await fetch(`/api/meetings/${meetingId}/turns/next`, { method: "POST" })
      if (!res.ok || !res.body) throw new Error(`请求失败：${res.status}`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      const parser = createSseParser(({ event, data }) => {
        if (event === "turn_done") {
          const payload = JSON.parse(data) as TurnInfo
          setTurnInfo(payload)
          if (!payload.done && autoPlayRef.current) {
            window.setTimeout(() => void runNextTurnRef.current(), 600)
          }
        } else {
          applyTurnEvent(event, data)
        }
      })
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        parser.push(decoder.decode(value, { stream: true }))
      }
    } catch {
      toast.error("执行发言失败，请重试")
    } finally {
      runningRef.current = false
      setTurnRunning(false)
    }
  }, [meetingId, applyTurnEvent])
  runNextTurnRef.current = runNextTurn

  const sendMessage = useCallback(
    async (content: string) => {
      if (!meetingId || !content.trim()) return false
      try {
        const msg = await api.sendMessage(meetingId, content)
        setMeeting((prev) => (prev ? { ...prev, messages: [...prev.messages, msg] } : prev))
        void runNextTurnRef.current()
        return true
      } catch {
        toast.error("发送失败，请重试")
        return false
      }
    },
    [meetingId],
  )

  return {
    meeting,
    connected,
    turnInfo,
    turnRunning,
    autoPlay,
    setAutoPlay,
    runNextTurn,
    sendMessage,
  }
}
```

- [ ] **Step 3: 构建验证**

```powershell
npm run build
npm run lint
```

Expected: 通过。若 lint 报 `runNextTurnRef.current = runNextTurn` 在渲染期赋值（react-hooks 规则不查这种 ref 赋值，一般不报），确认无 error 即可。

- [ ] **Step 4: Commit**

```powershell
git add web/frontend/src
git commit -m "feat(web): meeting list and room state hooks with sse reconnect"
```

---

### Task 5: 消息组件（MarkdownContent / MessageBubble / MessageList）

**Files:**
- Create: `web/frontend/src/components/MarkdownContent.tsx`、`web/frontend/src/components/MessageBubble.tsx`、`web/frontend/src/components/MessageList.tsx`

**Interfaces:**
- Consumes: Task 2 的 `.markdown-body` 样式；Task 3 的 `ChatMessage`/`Participant` 类型；shadcn `button`/`avatar`/`badge`。
- Produces:
  - `<MarkdownContent content={string} />`
  - `<MessageBubble msg={ChatMessage} participants={Participant[]} />`
  - `<MessageList meeting={Meeting} />`（含智能滚动 + 回到底部按钮）

- [ ] **Step 1: 写 src/components/MarkdownContent.tsx**

```tsx
import { useRef, useState, type ReactNode } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import { Check, Copy } from "lucide-react"
import { Button } from "@/components/ui/button"

function CodeBlock({ children }: { children?: ReactNode }) {
  const preRef = useRef<HTMLPreElement>(null)
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    const text = preRef.current?.textContent ?? ""
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // 剪贴板不可用时静默忽略
    }
  }

  return (
    <div className="group relative my-2">
      <Button
        variant="ghost"
        size="icon"
        className="absolute right-2 top-2 z-10 h-7 w-7 text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:bg-zinc-800 hover:text-zinc-100"
        onClick={() => void copy()}
      >
        {copied ? <Check className="h-3.5 w-3.5 text-green-400" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
      <pre ref={preRef} className="overflow-x-auto rounded-lg bg-zinc-950 p-4 text-xs leading-relaxed text-zinc-50">
        {children}
      </pre>
    </div>
  )
}

export function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="markdown-body min-w-0 break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-4">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-xs [&_td]:border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:px-2 [&_th]:py-1">
                {children}
              </table>
            </div>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
```

- [ ] **Step 2: 写 src/components/MessageBubble.tsx**

```tsx
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { MarkdownContent } from "@/components/MarkdownContent"
import { cn } from "@/lib/utils"
import type { ChatMessage, Participant } from "@/types"

export function MessageBubble({ msg, participants }: { msg: ChatMessage; participants: Participant[] }) {
  const isUser = msg.participant_id === "user"
  const isSystem = msg.participant_id === "system"
  const isJudge = msg.type === "judge"
  const avatar =
    participants.find((p) => p.id === msg.participant_id)?.avatar || (isSystem ? "🔔" : "💬")

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex max-w-[85%] gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
        <Avatar className="mt-1 h-9 w-9 rounded-lg border bg-background">
          <AvatarFallback className="rounded-lg text-lg">{avatar}</AvatarFallback>
        </Avatar>
        <div
          className={cn(
            "min-w-0 rounded-2xl px-4 py-3 text-sm",
            isUser && "bg-primary text-primary-foreground",
            isSystem && "border bg-muted text-muted-foreground",
            isJudge && "border-2 border-amber-500/60 bg-amber-500/5 shadow-sm",
            !isUser && !isSystem && !isJudge && "border bg-card",
          )}
        >
          <div className="mb-1 flex items-center gap-2 text-xs opacity-75">
            <span className="font-medium">{msg.participant_name}</span>
            <span>{msg.timestamp}</span>
            {isJudge && (
              <Badge variant="outline" className="border-amber-500/60 text-amber-600 dark:text-amber-400">
                裁判总结
              </Badge>
            )}
          </div>
          {isUser || isSystem ? (
            <div className="whitespace-pre-wrap break-words">{msg.content}</div>
          ) : (
            <MarkdownContent content={msg.content} />
          )}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 写 src/components/MessageList.tsx**

```tsx
import { useEffect, useRef, useState } from "react"
import { ArrowDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { MessageBubble } from "@/components/MessageBubble"
import type { Meeting } from "@/types"

export function MessageList({ meeting }: { meeting: Meeting }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [atBottom, setAtBottom] = useState(true)

  useEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [meeting.messages.length, atBottom])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80)
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-4xl space-y-4">
          {meeting.messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} participants={meeting.participants} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
      {!atBottom && (
        <Button
          size="icon"
          className="absolute bottom-4 right-6 rounded-full shadow-lg"
          onClick={() => {
            setAtBottom(true)
            bottomRef.current?.scrollIntoView({ behavior: "smooth" })
          }}
        >
          <ArrowDown />
        </Button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: 构建验证**

```powershell
npm run build
npm run lint
```

Expected: 通过。

- [ ] **Step 5: Commit**

```powershell
git add web/frontend/src
git commit -m "feat(web): markdown content, message bubble and smart-scroll list"
```

---

### Task 6: 会议室视图组件（RoomHeader / ParticipantBar / TurnControlBar / ChatInput）

**Files:**
- Create: `web/frontend/src/components/RoomHeader.tsx`、`web/frontend/src/components/ParticipantBar.tsx`、`web/frontend/src/components/TurnControlBar.tsx`、`web/frontend/src/components/ChatInput.tsx`

**Interfaces:**
- Consumes: Task 3 类型与 `modeBadgeTextFull`；Task 4 的 `TurnInfo` 形状；Task 2 的 `.thinking-dot`。
- Produces:
  - `<RoomHeader meeting={Meeting | null} connected={boolean} onClose={() => void} />`
  - `<ParticipantBar participants={Participant[]} />`
  - `<TurnControlBar turnInfo={TurnInfo | null} turnRunning={boolean} autoPlay={boolean} onToggleAutoPlay={(v: boolean) => void} onContinue={() => void} />`
  - `<ChatInput onSend={(content: string) => Promise<boolean>} />`

- [ ] **Step 1: 写 src/components/RoomHeader.tsx**

```tsx
import { ArrowLeft } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { modeBadgeTextFull } from "@/lib/labels"
import { cn } from "@/lib/utils"
import type { Meeting } from "@/types"

export function RoomHeader({
  meeting,
  connected,
  onClose,
}: {
  meeting: Meeting | null
  connected: boolean
  onClose: () => void
}) {
  return (
    <header className="border-b bg-card px-6 py-3">
      <div className="mx-auto flex max-w-4xl items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-2">
          <Button variant="ghost" size="icon" onClick={onClose} title="返回列表">
            <ArrowLeft />
          </Button>
          <div className="min-w-0">
            <h1 className="truncate font-bold leading-tight">{meeting?.topic ?? "加载中…"}</h1>
            {meeting && (
              <Badge variant="secondary" className="mt-1">
                {modeBadgeTextFull(meeting)}
              </Badge>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
          <span
            className={cn("h-2 w-2 rounded-full", connected ? "animate-pulse bg-green-500" : "bg-red-500")}
          />
          {connected ? "实时连接中" : "已断开"}
        </div>
      </div>
    </header>
  )
}
```

- [ ] **Step 2: 写 src/components/ParticipantBar.tsx**

```tsx
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"
import type { Participant } from "@/types"

function StatusText({ status }: { status: Participant["status"] }) {
  if (status === "thinking") {
    return (
      <span className="flex items-center gap-1 text-blue-500">
        思考中
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-blue-500" />
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-blue-500" />
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-blue-500" />
      </span>
    )
  }
  return (
    <span className={cn(status === "speaking" ? "text-green-600 dark:text-green-400" : "text-muted-foreground")}>
      {status === "speaking" ? "发言中" : "等待中"}
    </span>
  )
}

export function ParticipantBar({ participants }: { participants: Participant[] }) {
  return (
    <div className="border-b bg-muted/40 px-6 py-2">
      <div className="mx-auto flex max-w-4xl flex-wrap gap-2">
        {participants.map((p) => (
          <div
            key={p.id}
            className="flex items-center gap-2 rounded-full border bg-card py-1 pl-1 pr-3 shadow-sm"
          >
            <Avatar className="h-7 w-7 rounded-full border">
              <AvatarFallback className="text-sm">{p.avatar}</AvatarFallback>
            </Avatar>
            <div className="text-xs leading-tight">
              <div className="font-medium">{p.name}</div>
              <StatusText status={p.status} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 写 src/components/TurnControlBar.tsx**

```tsx
import { Loader2, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import type { TurnInfo } from "@/types"

export function TurnControlBar({
  turnInfo,
  turnRunning,
  autoPlay,
  onToggleAutoPlay,
  onContinue,
}: {
  turnInfo: TurnInfo | null
  turnRunning: boolean
  autoPlay: boolean
  onToggleAutoPlay: (value: boolean) => void
  onContinue: () => void
}) {
  if (!turnInfo || turnInfo.done || !turnInfo.next) return null

  return (
    <div className="border-b bg-primary/5 px-6 py-2">
      <div className="mx-auto flex max-w-4xl items-center gap-3 text-sm">
        <span className="font-medium">
          下一位发言：{turnInfo.next.avatar} {turnInfo.next.name}
        </span>
        <Button size="sm" onClick={onContinue} disabled={turnRunning}>
          {turnRunning ? <Loader2 className="animate-spin" /> : <Play />}
          继续
        </Button>
        <div className="ml-auto flex items-center gap-2">
          <Label htmlFor="autoplay-bar" className="text-xs text-muted-foreground">
            自动连播
          </Label>
          <Switch
            id="autoplay-bar"
            checked={autoPlay}
            onCheckedChange={(v) => {
              onToggleAutoPlay(v)
              if (v && !turnRunning) onContinue()
            }}
          />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 写 src/components/ChatInput.tsx**

```tsx
import { useRef, useState, type KeyboardEvent } from "react"
import { Loader2, SendHorizontal } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

export function ChatInput({ onSend }: { onSend: (content: string) => Promise<boolean> }) {
  const [value, setValue] = useState("")
  const [sending, setSending] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)

  const send = async () => {
    const content = value.trim()
    if (!content || sending) return
    setSending(true)
    const ok = await onSend(content)
    setSending(false)
    if (ok) {
      setValue("")
      ref.current?.focus()
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <footer className="border-t bg-card p-4">
      <div className="mx-auto flex max-w-4xl items-end gap-3">
        <Textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="继续提问或追加需求...（Enter 发送，Shift+Enter 换行）"
          rows={1}
          className="max-h-40 min-h-11 resize-none"
        />
        <Button
          size="icon"
          className="h-11 w-11 shrink-0"
          onClick={() => void send()}
          disabled={sending || !value.trim()}
        >
          {sending ? <Loader2 className="animate-spin" /> : <SendHorizontal />}
        </Button>
      </div>
    </footer>
  )
}
```

- [ ] **Step 5: 构建验证**

```powershell
npm run build
npm run lint
```

Expected: 通过（此时 App.tsx 仍是脚手架默认内容，未引用新组件，不影响构建）。

- [ ] **Step 6: Commit**

```powershell
git add web/frontend/src
git commit -m "feat(web): room header, participant bar, turn controls and chat input"
```

---

### Task 7: 侧边栏 / 创建对话框 / 首页 / App 装配 + 开发环境手工验收

**Files:**
- Create: `web/frontend/src/components/Sidebar.tsx`、`web/frontend/src/components/CreateMeetingDialog.tsx`、`web/frontend/src/components/HomeEmptyState.tsx`
- Modify: `web/frontend/src/App.tsx`（整体重写）

**Interfaces:**
- Consumes: Task 2 `ThemeToggle`、Task 3 `api`/`labels`/类型、Task 4 hooks、Task 5/6 全部视图组件。
- Produces: 完整可运行前端。`App` 状态：`meetingId: string | null`（驱动两视图与 URL 同步）。

- [ ] **Step 1: 写 src/components/Sidebar.tsx**

```tsx
import { useState } from "react"
import { Bot, MoreHorizontal, Plus } from "lucide-react"
import { ThemeToggle } from "@/components/ThemeToggle"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { modeBadgeText } from "@/lib/labels"
import { cn } from "@/lib/utils"
import type { MeetingSummary } from "@/types"

export function Sidebar({
  meetings,
  activeId,
  onOpen,
  onCreate,
  onDelete,
}: {
  meetings: MeetingSummary[]
  activeId: string | null
  onOpen: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}) {
  const [deleteTarget, setDeleteTarget] = useState<MeetingSummary | null>(null)

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r bg-card">
      <div className="border-b p-4">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-bold">
            <Bot className="h-5 w-5" />
            A2A 会议室
          </h2>
          <ThemeToggle />
        </div>
        <Button className="mt-3 w-full" onClick={onCreate}>
          <Plus />新建会议
        </Button>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {meetings.length === 0 && (
          <div className="py-8 text-center text-sm text-muted-foreground">暂无历史会议</div>
        )}
        {meetings.map((m) => (
          <div
            key={m.id}
            onClick={() => onOpen(m.id)}
            className={cn(
              "group cursor-pointer rounded-lg border p-3 transition-colors",
              m.id === activeId ? "border-primary/40 bg-accent" : "hover:bg-accent/50",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="truncate text-sm font-medium" title={m.topic}>
                {m.topic}
              </div>
              <DropdownMenu>
                <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 shrink-0 opacity-0 transition group-hover:opacity-100"
                  >
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                  <DropdownMenuItem variant="destructive" onClick={() => setDeleteTarget(m)}>
                    删除会议
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Badge variant="secondary" className="px-1.5 py-0">
                {modeBadgeText(m.mode, m.max_rounds)}
              </Badge>
              <span className="truncate">{m.created_at}</span>
            </div>
          </div>
        ))}
      </div>

      <AlertDialog open={deleteTarget !== null} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除会议室？</AlertDialogTitle>
            <AlertDialogDescription>
              「{deleteTarget?.topic}」及其全部消息将被永久删除，无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleteTarget) onDelete(deleteTarget.id)
                setDeleteTarget(null)
              }}
            >
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  )
}
```

- [ ] **Step 2: 写 src/components/CreateMeetingDialog.tsx**

```tsx
import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Meeting, MeetingMode, Persona } from "@/types"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"

const MODE_OPTIONS: ReadonlyArray<[MeetingMode, string, string]> = [
  ["pipeline", "流水线模式", "依次发言"],
  ["roundtable", "圆桌讨论", "Moderator 主持"],
  ["debate", "辩论模式", "人格对抗 + 裁判"],
]

export function CreateMeetingDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (meeting: Meeting) => void
}) {
  const [topic, setTopic] = useState("")
  const [mode, setMode] = useState<MeetingMode>("pipeline")
  const [maxRounds, setMaxRounds] = useState(1)
  const [autoPlay, setAutoPlay] = useState(false)
  const [proPersona, setProPersona] = useState("socrates")
  const [conPersona, setConPersona] = useState("hume")
  const [personas, setPersonas] = useState<Persona[]>([])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    api
      .listPersonas()
      .then(setPersonas)
      .catch(() => toast.error("加载人格列表失败"))
  }, [open])

  const roundsCap = mode === "debate" ? 3 : 10

  const submit = async () => {
    if (!topic.trim() || submitting) return
    setSubmitting(true)
    try {
      const meeting = await api.createMeeting({
        topic: topic.trim(),
        mode,
        max_rounds: mode === "pipeline" ? 1 : maxRounds,
        auto_play: autoPlay,
        pro_persona: proPersona,
        con_persona: conPersona,
      })
      setTopic("")
      setMaxRounds(1)
      setAutoPlay(false)
      onCreated(meeting)
    } catch {
      toast.error("创建会议失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建会议</DialogTitle>
          <DialogDescription>创建一个主题，邀请多个 Agent 一起讨论</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="topic">会议主题</Label>
            <Input
              id="topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void submit()}
              placeholder="输入会议主题，例如：A2A protocol"
            />
          </div>

          <div className="space-y-2">
            <Label>会议模式</Label>
            <RadioGroup value={mode} onValueChange={(v) => setMode(v as MeetingMode)} className="gap-2">
              {MODE_OPTIONS.map(([value, title, desc]) => (
                <Label
                  key={value}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 has-[[data-state=checked]]:border-primary"
                >
                  <RadioGroupItem value={value} className="mt-0.5" />
                  <span>
                    <span className="block font-medium">{title}</span>
                    <span className="block text-xs font-normal text-muted-foreground">{desc}</span>
                  </span>
                </Label>
              ))}
            </RadioGroup>
          </div>

          {(mode === "roundtable" || mode === "debate") && (
            <div className="space-y-2">
              <Label>
                {mode === "debate" ? "辩论轮数" : "讨论轮数"}：{maxRounds} 轮
              </Label>
              <Slider
                min={1}
                max={roundsCap}
                step={1}
                value={[maxRounds]}
                onValueChange={([v]) => setMaxRounds(v)}
              />
            </div>
          )}

          {mode === "debate" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>正方人格</Label>
                <Select value={proPersona} onValueChange={setProPersona}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {personas.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.avatar} {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>反方人格</Label>
                <Select value={conPersona} onValueChange={setConPersona}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {personas.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.avatar} {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between">
            <Label htmlFor="autoplay">自动连播</Label>
            <Switch id="autoplay" checked={autoPlay} onCheckedChange={setAutoPlay} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => void submit()} disabled={!topic.trim() || submitting}>
            {submitting && <Loader2 className="animate-spin" />}
            创建会议室
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 3: 写 src/components/HomeEmptyState.tsx**

```tsx
import { Bot } from "lucide-react"
import { Button } from "@/components/ui/button"

export function HomeEmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border bg-card p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <Bot className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-xl font-bold">A2A 多人会议室</h1>
        <p className="mt-2 text-sm text-muted-foreground">创建一个主题，邀请多个 Agent 一起讨论</p>
        <Button className="mt-6" onClick={onCreate}>
          新建会议
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: 重写 src/App.tsx**

```tsx
import { useCallback, useState } from "react"
import { ChatInput } from "@/components/ChatInput"
import { CreateMeetingDialog } from "@/components/CreateMeetingDialog"
import { HomeEmptyState } from "@/components/HomeEmptyState"
import { MessageList } from "@/components/MessageList"
import { ParticipantBar } from "@/components/ParticipantBar"
import { RoomHeader } from "@/components/RoomHeader"
import { Sidebar } from "@/components/Sidebar"
import { TurnControlBar } from "@/components/TurnControlBar"
import { useMeetings } from "@/hooks/useMeetings"
import { useMeetingRoom } from "@/hooks/useMeetingRoom"
import type { Meeting } from "@/types"

function updateUrl(meetingId: string | null) {
  const url = new URL(window.location.href)
  if (meetingId) url.searchParams.set("meeting", meetingId)
  else url.searchParams.delete("meeting")
  window.history.replaceState({}, "", url)
}

export default function App() {
  const [meetingId, setMeetingId] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("meeting"),
  )
  const [createOpen, setCreateOpen] = useState(false)
  const { meetings, refresh, remove } = useMeetings()
  const room = useMeetingRoom(meetingId)

  const openMeeting = useCallback((id: string) => {
    setMeetingId(id)
    updateUrl(id)
  }, [])

  const closeMeeting = useCallback(() => {
    setMeetingId(null)
    updateUrl(null)
  }, [])

  const handleCreated = useCallback(
    (meeting: Meeting) => {
      setCreateOpen(false)
      void refresh()
      openMeeting(meeting.id)
    },
    [refresh, openMeeting],
  )

  const handleDelete = useCallback(
    async (id: string) => {
      const ok = await remove(id)
      if (ok && id === meetingId) closeMeeting()
    },
    [remove, meetingId, closeMeeting],
  )

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar
        meetings={meetings}
        activeId={meetingId}
        onOpen={openMeeting}
        onCreate={() => setCreateOpen(true)}
        onDelete={(id) => void handleDelete(id)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        {!meetingId ? (
          <HomeEmptyState onCreate={() => setCreateOpen(true)} />
        ) : (
          <>
            <RoomHeader meeting={room.meeting} connected={room.connected} onClose={closeMeeting} />
            {room.meeting && <ParticipantBar participants={room.meeting.participants} />}
            <TurnControlBar
              turnInfo={room.turnInfo}
              turnRunning={room.turnRunning}
              autoPlay={room.autoPlay}
              onToggleAutoPlay={room.setAutoPlay}
              onContinue={() => void room.runNextTurn()}
            />
            {room.meeting ? (
              <MessageList meeting={room.meeting} />
            ) : (
              <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
                正在加载会议室…
              </div>
            )}
            <ChatInput onSend={room.sendMessage} />
          </>
        )}
      </div>
      <CreateMeetingDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={handleCreated}
      />
    </div>
  )
}
```

- [ ] **Step 5: 构建验证**

```powershell
npm run build
npm run lint
```

Expected: 通过。

- [ ] **Step 6: 开发环境手工验收**

终端 1（仓库根目录）：`uv run python web/main.py`（FastAPI 于 8080，测试无需 LLM key，走 fallback 回复）。
终端 2（workdir=`web/frontend`）：`npm run dev`，浏览器打开 `http://localhost:5173`，逐项检查：

1. 侧边栏列出历史会议；首页显示空状态卡片
2. 「新建会议」打开 Dialog：RadioGroup 三模式、roundtable/debate 出现轮数 Slider（上限 3/10）、debate 出现人格 Select、Switch 自动连播
3. 创建 pipeline 会议 → 进入房间，SSE init 后顶栏显示主题与模式 Badge、绿色连接点、参与者条
4. 点「继续」→ agent thinking 动画 → 发言消息（Markdown 渲染、代码块深色 + 复制按钮）
5. 开自动连播 Switch → 连续推进；关掉 → 回到步进；turn 进行中「继续」按钮转圈
6. 输入框 Enter 发送插话、Shift+Enter 换行；消息发出后自动触发下一轮
7. 消息多时向上滚动 → 自动滚停 + 右下角「↓」按钮 → 点击回底部
8. 辩论模式会议：创建（选人格）→ 推进 → 裁判消息金色边框卡片 + 「裁判总结」Badge
9. 侧边栏卡片 `⋯` → 删除 → AlertDialog 确认 → 列表移除
10. 右上角主题菜单：亮/暗/跟随系统切换，暗色下整体协调
11. 新标签直接打开 `http://localhost:5173/?meeting=<已存在id>` → 直接进入房间

Expected: 全部通过。发现问题当场修复后重跑构建。

- [ ] **Step 7: Commit**

```powershell
git add web/frontend/src
git commit -m "feat(web): sidebar, create dialog, home state and app assembly"
```

---

### Task 8: FastAPI 托管 dist + 删除旧静态页 + Docker 多阶段 + README

**Files:**
- Modify: `web/main.py`（imports 约 14-16 行、`serve_react` 约 544-549 行）
- Delete: `web/static/`（整个目录）
- Modify: `web/Dockerfile`（重写）、`README.md`、`README.zh-CN.md`

**Interfaces:**
- Consumes: Task 1-7 的 `web/frontend/dist/` 构建产物。
- Produces: `GET /` 返回 `dist/index.html`（dist 缺失时返回 200 占位页，满足 `test_web.py` 的 `wait_for_ready`）；`/assets/*` 静态挂载；Docker 镜像自包含前端产物。

- [ ] **Step 1: 修改 web/main.py 的 imports**

在 `from fastapi.responses import StreamingResponse, FileResponse` 一行中加入 `HTMLResponse`，并新增 StaticFiles 导入：

```python
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
```

- [ ] **Step 2: 替换 serve_react 与资产挂载**

将原（约 544-549 行）：

```python
@app.get("/")
async def serve_react():
    static_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "static", "index.html"
    )
    return FileResponse(static_file)
```

替换为：

```python
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
ASSETS_DIR = os.path.join(DIST_DIR, "assets")


@app.get("/")
async def serve_react():
    index_file = os.path.join(DIST_DIR, "index.html")
    if not os.path.exists(index_file):
        return HTMLResponse(
            "<h1>A2A 多人会议室</h1>"
            "<p>前端尚未构建。请运行：</p>"
            "<pre>cd web/frontend &amp;&amp; npm install &amp;&amp; npm run build</pre>",
        )
    return FileResponse(index_file)


if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
```

- [ ] **Step 3: 删除 web/static**

```powershell
Remove-Item -Recurse -Force web\static
```

（先 `git rm -r web/static` 或直接删除后由 git status 反映；`web/static/__pycache__` 一并消失。）

- [ ] **Step 4: 重写 web/Dockerfile（多阶段）**

```dockerfile
FROM node:20-slim AS frontend

WORKDIR /app/frontend

COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci
COPY web/frontend/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv==0.5.9

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY shared/ ./shared/
COPY web/main.py web/db.py web/turns.py ./web/
COPY --from=frontend /app/frontend/dist ./web/frontend/dist

CMD ["python", "web/main.py"]
```

- [ ] **Step 5: 更新 README**

在 `README.md` 与 `README.zh-CN.md` 的 Web/会议室相关章节（或"快速开始"之后）加入前端开发说明（中文版示例）：

```markdown
### 前端（web/frontend）

Web UI 使用 Vite + React + Tailwind + shadcn/ui 构建，产物由 FastAPI 托管。

\```bash
# 开发模式（需先启动后端 uv run python web/main.py）
cd web/frontend
npm install
npm run dev        # http://localhost:5173，/api 自动代理到 8080

# 生产构建
npm run build      # 产物输出 web/frontend/dist，FastAPI 自动托管
\```

Docker 镜像构建时自动完成前端构建，无需手动操作。
```

（英文版在对应位置加入以下内容，标题为 `### Frontend (web/frontend)`，正文：）

```markdown
### Frontend (web/frontend)

The web UI is built with Vite + React + Tailwind + shadcn/ui and served by FastAPI.

\```bash
# Dev mode (start the backend first: uv run python web/main.py)
cd web/frontend
npm install
npm run dev        # http://localhost:5173, /api is proxied to :8080

# Production build
npm run build      # outputs web/frontend/dist, served automatically by FastAPI
\```

The Docker image builds the frontend automatically — no manual step required.
```

- [ ] **Step 6: 后端回归验证**

```powershell
npm run build
uv run ruff check .
uv run python test_web.py
```

（前两条 workdir 分别为 `web/frontend` 与仓库根。）

Expected: build 成功；ruff 无告警；test_web.py 打印 `Web A2A integration test passed!`（它自起服务于 8080，`/` 无 dist 也能 200）。

- [ ] **Step 7: 本地整体验证（FastAPI 托管 dist）**

```powershell
uv run python web/main.py
```

浏览器打开 `http://localhost:8080/`：应看到 shadcn 版界面（不再是 5173 dev server）；抽查 `?meeting=` 直开与暗色切换。

- [ ] **Step 8: Docker 构建验证**

```powershell
docker compose build web
```

Expected: node 阶段 `npm ci && npm run build` 成功，最终镜像生成。若本机 docker 不可用，记录并留待 CI/有 docker 的环境验证，不阻塞。

- [ ] **Step 9: Commit**

```powershell
git add -A
git commit -m "feat(web): serve built frontend from fastapi, multi-stage docker build"
```

---

### Task 9: 最终验收清单 + 收尾

**Files:**
- Modify: 仅验收中发现问题时的修复文件

**Interfaces:**
- Consumes: Task 1-8 全部产出。
- Produces: 与设计文档验收清单一致的通过记录；修复提交（如有）。

- [ ] **Step 1: 对照设计文档跑完整验收**

以 Task 8 Step 7 的方式跑生产构建（8080 直访），完整执行设计文档「测试与验收」9 项：三模式创建、步进/连播/插话、裁判消息样式、AlertDialog 删除、主题切换、`/?meeting=` 直开、断网重连提示、`npm run build` 产物托管、`docker compose build web`。

- [ ] **Step 2: 全量回归**

```powershell
uv run ruff check .
uv run pytest test_web_scheduler.py test_web_turns.py -q
npm run lint
npm run build
```

Expected: 全部通过（web 相关 pytest 不涉静态页，应保持绿色）。

- [ ] **Step 3: 收尾提交（如有修复）**

```powershell
git add -A
git commit -m "fix(web): frontend acceptance fixes"
```

（若无修复则跳过。）
