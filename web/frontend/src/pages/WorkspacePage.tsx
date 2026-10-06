import { useCallback, useEffect, useRef, useState } from "react"
import type { ReactNode, UIEvent } from "react"
import { AlertTriangle, ArrowLeft, Loader2, Pause } from "lucide-react"
import { toast } from "sonner"
import { DecisionGate } from "@/components/v2/DecisionGate"
import { DemoBadge } from "@/components/v2/StatusBadge"
import { InterventionBar } from "@/components/v2/InterventionBar"
import { MeetingPod } from "@/components/v2/MeetingPod"
import { OutcomeRail } from "@/components/v2/OutcomeRail"
import { Shell } from "@/components/v2/Shell"
import { StageTimeline } from "@/components/v2/StageTimeline"
import { StatusBadge } from "@/components/v2/StatusBadge"
import { ThemeToggle } from "@/components/v2/ThemeToggle"
import { TurnCard } from "@/components/v2/TurnCard"
import { UserNoteCard } from "@/components/v2/UserNoteCard"
import { useV2Stream } from "@/hooks/useV2Stream"
import { useHashRoute } from "@/lib/router"
import { STAGE_LABELS, STAGE_ORDER } from "@/lib/roles"
import { endTask, resumeTask, retryTask, type V2TaskT } from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
const PIN_THRESHOLD = 80

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}

export function WorkspacePage({ id }: { id: string }) {
  const { task, connected, error, focusSeq, refresh } = useV2Stream(id)
  const { navigate } = useHashRoute()
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const pinnedRef = useRef(true)
  const jumpTimerRef = useRef<number | null>(null)
  const [jumpSeq, setJumpSeq] = useState<number | null>(null)
  const [endOpen, setEndOpen] = useState(false)
  const [ending, setEnding] = useState(false)
  const [acting, setActing] = useState(false)
  const [followUp] = useState(() => {
    const raw = sessionStorage.getItem("v2FollowUp")
    if (raw === null) return ""
    sessionStorage.removeItem("v2FollowUp")
    return raw
  })

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

  useEffect(
    () => () => {
      if (jumpTimerRef.current !== null) window.clearTimeout(jumpTimerRef.current)
    },
    [],
  )

  const jumpToTurn = useCallback((seq: number) => {
    const el = scrollRef.current?.querySelector(`[data-seq="${seq}"]`)
    if (!el) return
    el.scrollIntoView({ block: "center", behavior: "smooth" })
    setJumpSeq(seq)
    if (jumpTimerRef.current !== null) window.clearTimeout(jumpTimerRef.current)
    jumpTimerRef.current = window.setTimeout(() => setJumpSeq(null), 2000)
  }, [])

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    const el = event.currentTarget
    pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < PIN_THRESHOLD
  }

  const handleDecided = (_updated: V2TaskT, uncertain: boolean) => {
    if (uncertain) {
      toast.info("已记录你的保留意见 · 接下来继续比较影响，稍后将再次请你选择")
    }
    refresh()
  }

  const handleRetry = async () => {
    if (!task || acting) return
    setActing(true)
    try {
      await retryTask(task.id)
      refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "重试失败，请稍后再试")
    } finally {
      setActing(false)
    }
  }

  const handleResume = async () => {
    if (!task || acting) return
    setActing(true)
    try {
      await resumeTask(task.id)
      refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "恢复失败，请稍后再试")
    } finally {
      setActing(false)
    }
  }

  const confirmEnd = async () => {
    if (!task || ending) return
    setEnding(true)
    try {
      await endTask(task.id)
      toast.success("已生成成果草稿")
      setEndOpen(false)
      navigate(`#/task/${task.id}/outcome`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败，请稍后再试")
    } finally {
      setEnding(false)
    }
  }

  useEffect(() => {
    if (!endOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setEndOpen(false)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [endOpen])

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
  const openDecision = task.decisions.find((decision) => decision.status === "open")
  const interventionDisabled =
    task.status === "preparing" || task.status === "completed" || task.status === "failed"

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
    const highlighted =
      (focusSeq !== null && turn.seq === focusSeq) || (jumpSeq !== null && turn.seq === jumpSeq)
    items.push(
      turn.kind === "user_note" || turn.kind === "decision_record" ? (
        <UserNoteCard key={turn.id} turn={turn} />
      ) : (
        <TurnCard key={turn.id} turn={turn} highlight={highlighted} />
      ),
    )
  }

  const statusBanner =
    task.status === "failed" ? (
      <div
        role="alert"
        className="flex flex-wrap items-center gap-3 rounded-[14px] border border-destructive/40 bg-destructive/10 p-4"
      >
        <AlertTriangle className="size-[18px] shrink-0 text-destructive" aria-hidden />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-sm font-bold text-destructive">讨论在生成发言时失败</span>
          {task.error ? (
            <span className="truncate text-xs text-destructive/80">{task.error}</span>
          ) : null}
        </div>
        <button
          type="button"
          disabled={acting}
          onClick={() => void handleRetry()}
          className={cn(
            "shrink-0 rounded-lg border border-destructive/40 px-3 py-1.5 text-[13px] font-bold text-destructive transition-colors hover:bg-destructive/10 disabled:pointer-events-none disabled:opacity-50",
            FOCUS_RING,
          )}
        >
          重试
        </button>
      </div>
    ) : task.status === "paused" ? (
      <div
        role="alert"
        className="flex flex-wrap items-center gap-3 rounded-[14px] border border-warning-border bg-warning-bg p-4"
      >
        <Pause className="size-[18px] shrink-0 text-warning" aria-hidden />
        <span className="min-w-0 flex-1 text-sm font-bold text-warning">已暂停</span>
        <button
          type="button"
          disabled={acting}
          onClick={() => void handleResume()}
          className={cn(
            "shrink-0 rounded-lg border border-warning-border px-3 py-1.5 text-[13px] font-bold text-warning transition-colors hover:bg-warning-bg/60 disabled:pointer-events-none disabled:opacity-50",
            FOCUS_RING,
          )}
        >
          继续讨论
        </button>
      </div>
    ) : null

  return (
    <Shell
      title={task.goal_text}
      subtitle={`${stageLabel(task.current_stage)} · 第 ${stageIndex + 1} / 4 阶段`}
      topRight={
        <div className="flex items-center gap-3">
          {task.demo ? <DemoBadge /> : null}
          <StatusBadge status={task.status} />
          <button
            type="button"
            disabled={!canEnd}
            onClick={() => setEndOpen(true)}
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
          {!connected ? (
            <div
              role="status"
              className="flex items-center gap-2 rounded-[14px] border border-border bg-panel p-4 text-[13px] text-muted-foreground"
            >
              <Loader2 className="size-4 animate-spin" aria-hidden />
              连接中断，正在重连…
            </div>
          ) : null}
          {statusBanner}
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
              {openDecision ? (
                <DecisionGate
                  key={`${openDecision.id}:${openDecision.round}`}
                  task={task}
                  decision={openDecision}
                  onDecided={handleDecided}
                />
              ) : null}
            </section>
          )}
          <InterventionBar
            taskId={task.id}
            status={task.status}
            disabled={interventionDisabled}
            prefill={followUp}
          />
        </section>
        <aside className="w-full shrink-0 xl:w-[336px]">
          <OutcomeRail task={task} onJumpToTurn={jumpToTurn} />
        </aside>
      </div>
      {endOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
          <button
            type="button"
            aria-label="取消结束协作"
            onClick={() => setEndOpen(false)}
            className="absolute inset-0 h-full w-full cursor-default bg-black/40"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="结束协作"
            className="relative flex w-full max-w-[420px] flex-col gap-4 rounded-[14px] border border-border bg-card p-6"
          >
            <h2 className="text-lg font-bold text-foreground">结束协作？</h2>
            <p className="text-sm text-secondary-foreground">
              将基于已有讨论立即生成成果草稿。
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setEndOpen(false)}
                className={cn(
                  "h-10 rounded-lg border border-border bg-card px-4 text-sm font-medium text-foreground transition-colors hover:bg-panel",
                  FOCUS_RING,
                )}
              >
                取消
              </button>
              <button
                type="button"
                disabled={ending}
                onClick={() => void confirmEnd()}
                className={cn(
                  "flex h-10 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-bold text-primary-foreground transition-colors disabled:pointer-events-none disabled:opacity-50",
                  FOCUS_RING,
                )}
              >
                {ending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
                确认结束
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </Shell>
  )
}
