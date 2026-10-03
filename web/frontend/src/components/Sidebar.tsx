import { useState } from "react"
import { MoreHorizontal, Plus, Search } from "lucide-react"
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
  online,
  onOpen,
  onCreate,
  onDelete,
}: {
  meetings: MeetingSummary[]
  activeId: string | null
  online: boolean | null
  onOpen: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}) {
  const [deleteTarget, setDeleteTarget] = useState<MeetingSummary | null>(null)
  const [query, setQuery] = useState("")
  const shown = query.trim()
    ? meetings.filter((m) => m.topic.toLowerCase().includes(query.trim().toLowerCase()))
    : meetings

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r bg-sidebar">
      <div className="p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-[10px] bg-primary font-extrabold text-primary-foreground shadow-glow">
              A²
            </div>
            <div>
              <div className="text-sm font-bold leading-tight">A2A 会议室</div>
              <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted-foreground">
                AGENT ROUNDTABLE
              </div>
            </div>
          </div>
          <ThemeToggle />
        </div>
        <Button className="mt-5 w-full gap-2" onClick={onCreate}>
          <Plus />新建会议
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto px-5 pb-4">
        <div className="flex items-center justify-between py-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
            最近会议 · {shown.length}
          </span>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索…"
              className="h-6 w-28 rounded-full border bg-background pl-6 pr-2 text-xs outline-none focus:border-primary"
            />
          </div>
        </div>
        <div className="space-y-2">
          {meetings.length === 0 && (
            <div className="py-8 text-center text-sm text-muted-foreground">暂无历史会议</div>
          )}
          {meetings.length > 0 && shown.length === 0 && (
            <div className="py-8 text-center text-sm text-muted-foreground">无匹配会议</div>
          )}
          {shown.map((m) => (
            <div
              key={m.id}
              onClick={() => onOpen(m.id)}
              className={cn(
                "group cursor-pointer rounded-[10px] border p-3 transition-colors",
                m.id === activeId
                  ? "border-primary/60 bg-accent"
                  : "border-transparent hover:bg-accent/50",
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
                  <DropdownMenuItem onClick={() => window.open(`/api/meetings/${m.id}/export`, "_blank")}>
                    导出记录
                  </DropdownMenuItem>
                  <DropdownMenuItem variant="destructive" onClick={() => setDeleteTarget(m)}>
                    删除会议
                  </DropdownMenuItem>
                </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                {modeBadgeText(m.mode, m.max_rounds)} · {m.created_at}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t p-5">
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              online === false ? "bg-destructive" : "bg-[#35d07f]",
              online !== false && "animate-pulse",
            )}
          />
          <div className="min-w-0 flex-1 leading-tight">
            <div className="text-xs font-medium">
              {online === false ? "服务连接失败" : "服务在线"}
            </div>
            <div className="truncate font-mono text-[9px] text-muted-foreground">
              A2A MESH · {meetings.length} SESSIONS
            </div>
          </div>
        </div>
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
