import { AlertTriangle, CheckCircle2, CircleHelp, Clock, MessagesSquare, Pause } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface BadgeConfigT {
  label: string
  icon: LucideIcon
  className: string
}

const BADGE_CONFIG: Record<string, BadgeConfigT> = {
  preparing: {
    label: "准备中",
    icon: Clock,
    className: "bg-panel text-muted-foreground",
  },
  running: {
    label: "进行中",
    icon: MessagesSquare,
    className: "bg-accent text-primary",
  },
  waiting_confirmation: {
    label: "等待你确认",
    icon: CircleHelp,
    className: "bg-warning-bg text-warning",
  },
  paused: {
    label: "已暂停",
    icon: Pause,
    className: "bg-panel text-muted-foreground",
  },
  completed: {
    label: "已完成",
    icon: CheckCircle2,
    className: "bg-success-bg text-success",
  },
  failed: {
    label: "失败",
    icon: AlertTriangle,
    className: "bg-destructive/10 text-destructive",
  },
}

export function StatusBadge({ status, sub }: { status: string; sub?: string }) {
  const config = BADGE_CONFIG[status] ?? {
    label: status,
    icon: Clock,
    className: "bg-panel text-muted-foreground",
  }
  const Icon = config.icon
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-lg px-[9px] py-[3px] text-xs font-medium",
        config.className,
      )}
    >
      <Icon className="size-3" aria-hidden />
      {config.label}
      {sub ? <span className="text-muted-foreground">· {sub}</span> : null}
    </span>
  )
}
