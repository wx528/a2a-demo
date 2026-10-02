import { ArrowLeft } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Eyebrow } from "@/components/Eyebrow"
import { modeBadgeTextFull } from "@/lib/labels"
import { cn } from "@/lib/utils"
import type { Meeting } from "@/types"

export function RoomHeader({
  meeting,
  connected,
  sseLatencyMs,
  onClose,
}: {
  meeting: Meeting | null
  connected: boolean
  sseLatencyMs: number | null
  onClose: () => void
}) {
  return (
    <header className="border-b bg-card/60 px-6 py-3 backdrop-blur">
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="ghost" size="icon" onClick={onClose} title="返回列表">
            <ArrowLeft />
          </Button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-lg font-extrabold leading-tight">
                {meeting?.topic ?? "加载中…"}
              </h2>
              {meeting && (
                <Badge variant="secondary" className="shrink-0 font-mono text-[10px]">
                  {modeBadgeTextFull(meeting)}
                </Badge>
              )}
            </div>
            {meeting && (
              <Eyebrow>
                SESSION {meeting.id.toUpperCase()} · {modeBadgeTextFull(meeting)}
              </Eyebrow>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 font-mono text-xs text-muted-foreground">
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              connected ? "animate-pulse bg-[#35d07f]" : "bg-destructive",
            )}
          />
          {connected ? `实时连接中${sseLatencyMs !== null ? ` · ${sseLatencyMs}ms` : ""}` : "已断开"}
        </div>
      </div>
    </header>
  )
}
