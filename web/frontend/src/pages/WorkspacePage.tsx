import { useEffect, useRef } from "react"
import type { ReactNode, UIEvent } from "react"
import { ArrowLeft, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { MeetingPod } from "@/components/v2/MeetingPod"
import { Shell } from "@/components/v2/Shell"
import { StageTimeline } from "@/components/v2/StageTimeline"
import { StatusBadge } from "@/components/v2/StatusBadge"
import { ThemeToggle } from "@/components/v2/ThemeToggle"
import { TurnCard } from "@/components/v2/TurnCard"
import { UserNoteCard } from "@/components/v2/UserNoteCard"
import { useV2Stream } from "@/hooks/useV2Stream"
import { useHashRoute } from "@/lib/router"
import { STAGE_LABELS, STAGE_ORDER } from "@/lib/roles"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
const PIN_THRESHOLD = 80

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}

export function WorkspacePage({ id }: { id: string }) {
  const { task, error, focusSeq } = useV2Stream(id)
  const { navigate } = useHashRoute()
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const pinnedRef = useRef(true)

  const showDiscussion = task !== null && task.status !== "preparing"
  const turns = task?.turns ?? []
  const lastTurn = turns.length > 0 ? turns[turns.length - 1] : null
  const tailKey = lastTurn
    ? `${turns.length}:${lastTurn.body.length}:${lastTurn.title.length}`
    : "0"

  useEffect(() => {
    if (!showDiscussion) return
    const el = sentinelRef.current
    if (!el) return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) pinnedRef.current = true
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [showDiscussion])

  useEffect(() => {
    const el = scrollRef.current
    if (!el || !pinnedRef.current) return
    el.scrollTop = el.scrollHeight
  }, [tailKey])

  useEffect(() => {
    if (focusSeq === null || !showDiscussion) return
    const el = scrollRef.current?.querySelector(`[data-seq="${focusSeq}"]`)
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" })
  }, [focusSeq, showDiscussion])

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    const el = event.currentTarget
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < PIN_THRESHOLD
  }

  if (error) {
    return (
      <Shell title="决策工作区" topRight={<ThemeToggle />}>
        <div className="flex flex-col items-center justify-center gap-4 p-16">
          <p className="text-sm text-muted-foreground">{error}</p>
          <button
            type="button"
            onClick={() => navigate("#/")}
            className={cn(
              "flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[13px] text-foreground transition-colors hover:bg-panel",
              FOCUS_RING,
            )}
          >
            <ArrowLeft className="size-4" aria-hidden />
            返回首页
          </button>
        </div>
      </Shell>
    )
  }

  if (!task) {
    return (
      <Shell title="载入中…" topRight={<ThemeToggle />}>
        <div className="flex items-center justify-center p-16" role="status" aria-label="载入中">
          <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden />
        </div>
      </Shell>
    )
  }

  const stageIndex = Math.max(0, STAGE_ORDER.indexOf(task.current_stage))
  const canEnd =
    task.status === "running" || task.status === "waiting_confirmation" || task.status === "paused"

  const items: ReactNode[] = []
  let prevStage: string | null = null
  for (const turn of task.turns) {
    if (turn.stage !== prevStage) {
      prevStage = turn.stage
      const isCurrent = turn.stage === task.current_stage
      items.push(
        <div
          key={`group-${turn.stage}`}
          className="flex items-center justify-between gap-3 border-b border-border py-2"
        >
          <span className="text-[13px] font-bold text-success">
            {isCurrent ? "当前阶段" : "此前阶段"} · {stageLabel(turn.stage)}
          </span>
          <span className="text-xs text-muted-foreground">
            {isCurrent
              ? task.status === "waiting_confirmation"
                ? "等待你确认接入边界"
                : "自动推进中"
              : "已完成 · 保留关键发言"}
          </span>
        </div>,
      )
    }
    items.push(
      turn.kind === "user_note" || turn.kind === "decision_record" ? (
        <UserNoteCard key={turn.id} turn={turn} />
      ) : (
        <TurnCard
          key={turn.id}
          turn={turn}
          highlight={focusSeq !== null && turn.seq === focusSeq}
        />
      ),
    )
  }

  return (
    <Shell
      title={task.goal_text}
      subtitle={`${stageLabel(task.current_stage)} · 第 ${stageIndex + 1} / 4 阶段`}
      topRight={
        <div className="flex items-center gap-3">
          <StatusBadge status={task.status} />
          <button
            type="button"
            disabled={!canEnd}
            onClick={() => toast.info("将在下一步接入")}
            className={cn(
              "rounded-lg px-3 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-panel hover:text-foreground disabled:pointer-events-none disabled:opacity-50",
              FOCUS_RING,
            )}
          >
            结束协作
          </button>
          <ThemeToggle />
        </div>
      }
    >
      <div className="px-6 pt-6">
        <MeetingPod task={task} />
      </div>
      <div className="flex flex-col gap-6 p-6 xl:flex-row">
        <section className="mx-auto flex w-full min-w-0 max-w-[800px] flex-1 flex-col gap-4">
          {task.status === "preparing" ? (
            <div className="flex flex-col items-center justify-center gap-3 rounded-[14px] border border-border bg-card p-12">
              <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden />
              <p className="text-sm text-muted-foreground">计划已确认，讨论即将开始…</p>
            </div>
          ) : (
            <section className="flex flex-col gap-5 rounded-[14px] border border-border bg-card p-6">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-lg font-bold text-foreground">围绕目标的讨论</h2>
                <span className="shrink-0 text-xs text-muted-foreground">
                  在关键节点介入，而非逐条推进
                </span>
              </div>
              <StageTimeline current={task.current_stage} />
              <div
                ref={scrollRef}
                onScroll={handleScroll}
                className="flex max-h-[600px] flex-col gap-[18px] overflow-y-auto pr-1"
              >
                {items}
                {task.turns.length === 0 ? (
                  <p className="py-6 text-center text-xs text-muted-foreground">等待发言开始…</p>
                ) : null}
                <div ref={sentinelRef} aria-hidden className="h-px shrink-0" />
              </div>
              {/* Task 14: DecisionGate renders here when open decision exists */}
            </section>
          )}
          {/* Task 14: InterventionBar */}
        </section>
        <aside className="w-full shrink-0 xl:w-[336px]">
          <div className="flex flex-col gap-4 rounded-[14px] border border-border bg-card p-6">
            <div className="flex flex-col gap-1">
              <h2 className="text-lg font-bold text-foreground">成果草稿</h2>
              <p className="text-xs text-muted-foreground">随讨论更新 · 尚未形成最终建议</p>
            </div>
            <div className="flex flex-col gap-2.5" aria-hidden>
              <div className="h-3 w-3/4 animate-pulse rounded bg-panel" />
              <div className="h-3 w-full animate-pulse rounded bg-panel" />
              <div className="h-3 w-5/6 animate-pulse rounded bg-panel" />
              <div className="h-3 w-2/3 animate-pulse rounded bg-panel" />
            </div>
          </div>
        </aside>
      </div>
    </Shell>
  )
}
