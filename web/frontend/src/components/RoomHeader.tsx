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
