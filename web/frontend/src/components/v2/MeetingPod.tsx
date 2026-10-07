import { useState } from "react"
import { ChevronDown, ChevronUp, Loader2 } from "lucide-react"
import type { V2StreamTaskT } from "@/hooks/useV2Stream"
import { roleMetaFromTask } from "@/lib/roles"
import { cn } from "@/lib/utils"

const PURPOSE_ORDER = ["research", "propose", "challenge", "synthesize"] as const
const DEFAULT_POD_ROLES = ["ada", "turing", "linus", "sage"] as const

function podRoles(task: V2StreamTaskT): string[] {
  const ids = PURPOSE_ORDER.map((purpose) => task.assignments?.[purpose]).filter(Boolean)
  return ids.length > 0 ? ids : [...DEFAULT_POD_ROLES]
}

type RoleStateT = "thinking" | "speaking" | "waiting" | "done" | "idle"

const ROLE_STATE_META: Record<RoleStateT, { label: string; dot: string }> = {
  thinking: { label: "思考中…", dot: "bg-primary animate-pulse" },
  speaking: { label: "发言中", dot: "bg-primary animate-pulse" },
  waiting: { label: "等待确认", dot: "bg-warning" },
  done: { label: "已完成", dot: "bg-success" },
  idle: { label: "待命", dot: "bg-muted-foreground/40" },
}

function roleState(task: V2StreamTaskT, author: string, thinkingAuthor: string | null): RoleStateT {
  if (task.status === "running" && thinkingAuthor === author) return "thinking"
  const turns = task.turns
  const last = turns[turns.length - 1]
  if (
    task.status === "running" &&
    last &&
    last.author === author &&
    (last.live || last.kind === "statement")
  ) {
    return "speaking"
  }
  const spokeThisStage = turns.some(
    (turn) =>
      turn.author === author &&
      turn.kind === "statement" &&
      !turn.live &&
      turn.stage === task.current_stage,
  )
  if (spokeThisStage) return "done"
  if (task.status === "waiting_confirmation") return "waiting"
  if (task.status === "completed") return "done"
  if (turns.some((turn) => turn.author === author && turn.kind === "statement" && !turn.live)) {
    return "done"
  }
  return "idle"
}

function podSummary(task: V2StreamTaskT, thinkingAuthor: string | null): string {
  if (task.status === "waiting_confirmation") return "等待你确认"
  if (task.status === "preparing") return "准备开始"
  if (task.status === "paused") return "讨论已暂停"
  if (task.status === "failed") return "讨论中断"
  if (task.status === "completed") return "讨论已完成"
  if (thinkingAuthor) return `${roleMetaFromTask(task, thinkingAuthor).zh} 思考中…`
  const speaking = podRoles(task).find((role) => roleState(task, role, null) === "speaking")
  if (speaking) return `${roleMetaFromTask(task, speaking).zh} 发言中`
  return "讨论进行中"
}

function customExpertCount(task: V2StreamTaskT): number {
  return (task.experts ?? []).filter((expert) => expert.source === "custom").length
}

function podHeader(task: V2StreamTaskT, thinkingAuthor: string | null): string {
  const base = "会议舱 · 4 个专业视角"
  if (task.demo) return `${base} · ${podSummary(task, thinkingAuthor)} · 演示 · 非实时`
  const custom = customExpertCount(task)
  const customText = custom > 0 ? ` · 含 ${custom} 位外部专家` : ""
  const states = podRoles(task).map((role) => task.connections?.[role])
  if (states.some((state) => typeof state === "string" && state !== "demo")) {
    const up = states.filter((state) => state === "up").length
    return `${base} · ${podSummary(task, thinkingAuthor)}${customText} · Agent 在线 ${up}/4`
  }
  return `${base} · ${podSummary(task, thinkingAuthor)}${customText}`
}

export function MeetingPod({
  task,
  thinkingAuthor = null,
}: {
  task: V2StreamTaskT
  thinkingAuthor?: string | null
}) {
  const [open, setOpen] = useState(
    () => typeof window === "undefined" || window.innerWidth >= 1280,
  )
  return (
    <section className="rounded-[14px] border border-border bg-card">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <h2 className="truncate text-[13px] font-bold text-secondary-foreground">
          {podHeader(task, thinkingAuthor)}
        </h2>
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          aria-expanded={open}
          className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {open ? "收起会议舱" : "展开会议舱"}
          {open ? (
            <ChevronUp className="size-3.5" aria-hidden />
          ) : (
            <ChevronDown className="size-3.5" aria-hidden />
          )}
        </button>
      </div>
      {open ? (
        <div className="grid grid-cols-2 gap-3 p-4 pt-0 xl:grid-cols-4">
          {podRoles(task).map((role) => {
            const meta = roleMetaFromTask(task, role)
            const state = roleState(task, role, thinkingAuthor)
            const stateMeta = ROLE_STATE_META[state]
            const connectionDown = task.connections?.[role] === "down"
            return (
              <div
                key={role}
                className={cn(
                  "flex items-center gap-2 rounded-[10px] border bg-card px-3 py-2.5",
                  state === "thinking" ? "border-accent-border bg-accent/40" : "border-border",
                )}
              >
                <span className="shrink-0 text-xl" aria-hidden>
                  {meta.emoji}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] font-medium text-foreground">
                    {meta.zh} · {meta.en}
                  </span>
                  <span
                    className={cn(
                      "flex items-center gap-1 text-xs",
                      state === "thinking" ? "font-medium text-primary" : "text-muted-foreground",
                    )}
                  >
                    {state === "thinking" ? (
                      <Loader2 className="size-3 animate-spin" aria-hidden />
                    ) : null}
                    {connectionDown ? "连接中断" : stateMeta.label}
                  </span>
                </span>
                <span
                  className={cn(
                    "size-1.5 shrink-0 rounded-full",
                    connectionDown ? "bg-destructive" : stateMeta.dot,
                  )}
                  aria-hidden
                />
              </div>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}
