import { useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import type { V2StreamTaskT } from "@/hooks/useV2Stream"
import { roleMeta } from "@/lib/roles"
import { cn } from "@/lib/utils"

const POD_ROLES = ["ada", "turing", "linus", "sage"] as const

type RoleStateT = "speaking" | "waiting" | "done" | "idle"

const ROLE_STATE_META: Record<RoleStateT, { label: string; dot: string }> = {
  speaking: { label: "发言中", dot: "bg-primary animate-pulse" },
  waiting: { label: "等待确认", dot: "bg-warning" },
  done: { label: "已完成", dot: "bg-success" },
  idle: { label: "待命", dot: "bg-muted-foreground/40" },
}

function roleState(task: V2StreamTaskT, author: string): RoleStateT {
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

function podSummary(task: V2StreamTaskT): string {
  if (task.status === "waiting_confirmation") return "等待你确认"
  if (task.status === "preparing") return "准备开始"
  if (task.status === "paused") return "讨论已暂停"
  if (task.status === "failed") return "讨论中断"
  if (task.status === "completed") return "讨论已完成"
  const speaking = POD_ROLES.find((role) => roleState(task, role) === "speaking")
  if (speaking) return `${roleMeta(speaking).zh} 发言中`
  return "讨论进行中"
}

function podHeader(task: V2StreamTaskT): string {
  const base = "会议舱 · 4 个专业视角"
  if (task.demo) return `${base} · 演示 · 非实时`
  const states = POD_ROLES.map((role) => task.connections?.[role])
  if (states.some((state) => typeof state === "string" && state !== "demo")) {
    const up = states.filter((state) => state === "up").length
    return `${base} · ${podSummary(task)} · Agent 在线 ${up}/4`
  }
  return `${base} · ${podSummary(task)}`
}

export function MeetingPod({ task }: { task: V2StreamTaskT }) {
  const [open, setOpen] = useState(
    () => typeof window === "undefined" || window.innerWidth >= 1280,
  )
  return (
    <section className="rounded-[14px] border border-border bg-card">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <h2 className="truncate text-[13px] font-bold text-secondary-foreground">
          {podHeader(task)}
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
          {POD_ROLES.map((role) => {
            const meta = roleMeta(role)
            const stateMeta = ROLE_STATE_META[roleState(task, role)]
            const connectionDown = task.connections?.[role] === "down"
            return (
              <div
                key={role}
                className="flex items-center gap-2 rounded-[10px] border border-border bg-card px-3 py-2.5"
              >
                <span className="shrink-0 text-xl" aria-hidden>
                  {meta.emoji}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] font-medium text-foreground">
                    {meta.zh} · {meta.en}
                  </span>
                  <span className="text-xs text-muted-foreground">
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
