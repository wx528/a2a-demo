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
