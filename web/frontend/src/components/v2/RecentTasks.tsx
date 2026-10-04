import { FileText, MessagesSquare } from "lucide-react"
import { toast } from "sonner"
import { useV2Tasks } from "@/hooks/useV2Tasks"
import { useHashRoute } from "@/lib/router"
import { StatusBadge } from "@/components/v2/StatusBadge"
import type { V2TaskSummaryT } from "@/lib/v2api"

const PROGRESS_LINES: Record<string, string> = {
  preparing: "即将开始讨论",
  running: "讨论进行中",
  waiting_confirmation: "需要你确认关键选择",
  paused: "讨论已暂停",
  completed: "可回看成果",
  failed: "讨论中断，可重试",
}

function actionFor(task: V2TaskSummaryT): { label: string; href: string } {
  if (task.status === "completed") {
    return { label: "查看成果 →", href: `#/task/${task.id}/outcome` }
  }
  if (task.status === "waiting_confirmation") {
    return { label: "回答并继续 →", href: `#/task/${task.id}` }
  }
  if (task.status === "failed") {
    return { label: "重试讨论 →", href: `#/task/${task.id}` }
  }
  return { label: "进入讨论 →", href: `#/task/${task.id}` }
}

export function RecentTasks() {
  const { tasks, loading, error, reload } = useV2Tasks()
  const { navigate } = useHashRoute()
  const shown = tasks.slice(0, 3)

  return (
    <section className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-bold text-foreground">从上次的判断继续</h2>
        <button
          type="button"
          onClick={() => toast.info("全部成果视图建设中，可在列表中选择任务")}
          className="rounded-sm text-[13px] text-primary hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          查看全部成果 →
        </button>
      </div>
      {loading ? (
        <div>
          {[0, 1, 2].map((index) => (
            <div key={index} className="flex items-center gap-6 border-b border-border py-4">
              <div className="h-11 w-[42px] shrink-0 animate-pulse rounded-[10px] bg-panel" />
              <div className="flex w-[336px] max-w-full flex-col gap-2">
                <div className="h-4 w-3/4 animate-pulse rounded bg-panel" />
                <div className="h-3 w-1/2 animate-pulse rounded bg-panel" />
              </div>
              <div className="h-5 w-24 animate-pulse rounded-lg bg-panel" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-[10px] border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void reload()}
            className="rounded-lg border border-destructive/40 px-3 py-1 text-xs font-bold text-destructive transition-colors hover:bg-destructive/10 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            重试
          </button>
        </div>
      ) : shown.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-10 text-muted-foreground">
          <MessagesSquare className="size-8" aria-hidden />
          <p className="text-sm">还没有任务，从上面提出第一个目标</p>
        </div>
      ) : (
        <div>
          {shown.map((task) => {
            const action = actionFor(task)
            const isCompleted = task.status === "completed"
            const RowIcon = isCompleted ? FileText : MessagesSquare
            return (
              <button
                key={task.id}
                type="button"
                onClick={() => navigate(action.href)}
                className="flex w-full flex-wrap items-center gap-6 border-b border-border py-4 text-left transition-colors hover:bg-panel/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <span className="flex h-11 w-[42px] shrink-0 items-center justify-center rounded-[10px] bg-card">
                  <RowIcon className="size-[18px] text-muted-foreground" aria-hidden />
                </span>
                <span className="flex w-[336px] min-w-0 max-w-full flex-col gap-1">
                  <span className="truncate text-[15px] font-bold text-foreground">
                    {task.goal_text}
                  </span>
                  <span className="truncate text-[13px] text-muted-foreground">
                    {task.outcome_summary || "暂无成果摘要"}
                  </span>
                </span>
                <span className="flex min-w-0 flex-1 flex-col items-start gap-1">
                  <StatusBadge status={task.status} />
                  <span className="truncate text-[13px] text-secondary-foreground">
                    {PROGRESS_LINES[task.status] ?? task.current_stage}
                  </span>
                </span>
                <span className="shrink-0 text-sm font-medium text-primary">{action.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}
