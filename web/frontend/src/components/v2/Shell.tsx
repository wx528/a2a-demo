import { useEffect, useState } from "react"
import type { ReactNode } from "react"
import {
  FolderOpen,
  LockKeyhole,
  Menu,
  Plus,
  Search,
  Settings2,
  UsersRound,
  X,
} from "lucide-react"
import { toast } from "sonner"
import { useV2Tasks } from "@/hooks/useV2Tasks"
import { useHashRoute } from "@/lib/router"
import { cn } from "@/lib/utils"
import { DemoChip, StatusBadge } from "@/components/v2/StatusBadge"
import { ExpertPanel } from "@/components/v2/ExpertPanel"
import { ThemeToggle } from "@/components/v2/ThemeToggle"

const STATUS_LABELS: Record<string, string> = {
  preparing: "准备中",
  running: "进行中",
  waiting_confirmation: "等待你确认",
  paused: "已暂停",
  completed: "已完成",
  failed: "失败",
}

const ICON_BUTTON =
  "flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-panel hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

function taskHref(id: string, status: string) {
  return status === "completed" ? `#/task/${id}/outcome` : `#/task/${id}`
}

function SidebarContent({
  activeId,
  onNavigate,
  onOpenExperts,
}: {
  activeId: string | null
  onNavigate?: () => void
  onOpenExperts?: () => void
}) {
  const { tasks } = useV2Tasks()
  const { navigate } = useHashRoute()
  const [filterOpen, setFilterOpen] = useState(false)
  const [filter, setFilter] = useState("")
  const visible = tasks
    .filter((task) => (filterOpen && filter ? task.goal_text.includes(filter) : true))
    .slice(0, 8)

  return (
    <>
      <div className="flex min-h-0 flex-1 flex-col gap-5">
        <div className="flex items-center gap-3 px-1">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-primary font-mono text-[18px] font-bold text-white">
            A²
          </div>
          <div className="flex min-w-0 flex-col">
            <span className="text-[17px] leading-tight font-bold text-foreground">A2A 会议室</span>
            <span className="text-xs text-muted-foreground">目标驱动的 AI 协作室</span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            navigate("#/")
            onNavigate?.()
          }}
          className="flex h-11 w-full shrink-0 items-center justify-center gap-2 rounded-lg bg-primary text-sm font-bold text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <Plus className="size-4" aria-hidden />
          开始新任务
        </button>
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-[13px] font-bold text-muted-foreground">任务与成果</span>
            <button
              type="button"
              aria-label={filterOpen ? "关闭搜索" : "搜索任务"}
              aria-expanded={filterOpen}
              onClick={() => {
                setFilterOpen((prev) => !prev)
                setFilter("")
              }}
              className={ICON_BUTTON}
            >
              <Search className="size-4" aria-hidden />
            </button>
          </div>
          {filterOpen && (
            <input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="搜索任务"
              aria-label="搜索任务"
              className="h-8 w-full shrink-0 rounded-lg border border-border bg-card px-2.5 text-xs text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
            />
          )}
          <nav
            aria-label="任务与成果列表"
            className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto"
          >
            {visible.map((task) => (
              <button
                key={task.id}
                type="button"
                onClick={() => {
                  navigate(taskHref(task.id, task.status))
                  onNavigate?.()
                }}
                className={cn(
                  "flex flex-col gap-2 rounded-[10px] border border-transparent p-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  activeId === task.id
                    ? "border-accent-border bg-accent"
                    : "hover:bg-panel",
                )}
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className="truncate text-sm font-medium text-foreground">
                    {task.goal_text}
                  </span>
                  {task.demo ? <DemoChip /> : null}
                </span>
                <StatusBadge status={task.status} />
                <span className="truncate text-xs text-muted-foreground">
                  {task.outcome_summary || STATUS_LABELS[task.status] || task.status}
                </span>
              </button>
            ))}
            {visible.length === 0 && (
              <p className="px-3 py-2 text-xs text-muted-foreground">暂无匹配任务</p>
            )}
          </nav>
          <button
            type="button"
            onClick={() => toast.info("全部成果视图建设中，可在列表中选择任务")}
            className="flex shrink-0 items-center gap-2 rounded-lg px-1 py-2 text-[13px] text-secondary-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <FolderOpen className="size-4" aria-hidden />
            查看全部成果
          </button>
          <button
            type="button"
            onClick={onOpenExperts}
            className="flex shrink-0 items-center gap-2 rounded-lg px-1 py-2 text-[13px] text-secondary-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <UsersRound className="size-4" aria-hidden />
            专家库
          </button>
        </div>
      </div>
      <div className="flex shrink-0 flex-col gap-3 pt-4">
        <div className="flex items-start gap-2.5 rounded-[10px] bg-card p-3">
          <LockKeyhole className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <div className="flex flex-col">
            <span className="text-[13px] font-medium text-foreground">团队私有工作区</span>
            <span className="text-xs text-muted-foreground">讨论与成果保存在此工作区</span>
          </div>
        </div>
        <div className="flex items-center gap-2.5 px-1">
          <div
            className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-primary"
            aria-hidden
          >
            我
          </div>
          <span className="flex-1 text-[13px] text-foreground">我的工作区</span>
          <button
            type="button"
            aria-label="设置"
            onClick={() => toast.info("设置建设中")}
            className={ICON_BUTTON}
          >
            <Settings2 className="size-4" aria-hidden />
          </button>
        </div>
      </div>
    </>
  )
}

export function Shell({
  title,
  subtitle,
  topRight,
  children,
}: {
  title: string
  subtitle?: string
  topRight?: ReactNode
  children: ReactNode
}) {
  const { route } = useHashRoute()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [expertPanelOpen, setExpertPanelOpen] = useState(false)
  const activeId = route.name === "task" || route.name === "outcome" ? route.id : null

  useEffect(() => {
    if (!drawerOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [drawerOpen])

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-[232px] shrink-0 flex-col justify-between border-r border-border bg-sidebar px-4 pt-7 pb-6 lg:flex">
        <SidebarContent
          activeId={activeId}
          onOpenExperts={() => setExpertPanelOpen(true)}
        />
      </aside>
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="关闭侧栏"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 h-full w-full cursor-default bg-black/40"
          />
          <aside className="absolute inset-y-0 left-0 flex w-[280px] flex-col overflow-y-auto border-r border-border bg-sidebar px-4 pt-5 pb-6">
            <div className="mb-3 flex justify-end">
              <button
                type="button"
                aria-label="关闭侧栏"
                onClick={() => setDrawerOpen(false)}
                className={ICON_BUTTON}
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>
            <SidebarContent
              activeId={activeId}
              onNavigate={() => setDrawerOpen(false)}
              onOpenExperts={() => setExpertPanelOpen(true)}
            />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-[88px] shrink-0 items-center justify-between border-b border-border bg-card px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              aria-label="打开侧栏"
              onClick={() => setDrawerOpen(true)}
              className={cn(ICON_BUTTON, "lg:hidden")}
            >
              <Menu className="size-5" aria-hidden />
            </button>
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-[17px] font-bold text-foreground">{title}</span>
              {subtitle ? (
                <span className="truncate text-xs text-muted-foreground">{subtitle}</span>
              ) : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center">{topRight ?? <ThemeToggle />}</div>
        </header>
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
      <ExpertPanel open={expertPanelOpen} onClose={() => setExpertPanelOpen(false)} />
    </div>
  )
}
