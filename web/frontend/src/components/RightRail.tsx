import { Check } from "lucide-react"
import { Eyebrow } from "@/components/Eyebrow"
import type { ProgressView } from "@/lib/sequence"
import { cn } from "@/lib/utils"
import type { Meeting } from "@/types"

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[20px] border bg-card p-[18px]">
      <Eyebrow>{title}</Eyebrow>
      <div className="mt-3">{children}</div>
    </div>
  )
}

export function RightRail({
  meeting,
  progress,
  sseLatencyMs,
}: {
  meeting: Meeting
  progress: ProgressView
  sseLatencyMs: number | null
}) {
  const progressSlots = progress.slots

  const speakCount = new Map<string, number>()
  let chars = 0
  for (const m of meeting.messages) {
    if (m.type !== "message") continue
    if (m.participant_id !== "user" && m.participant_id !== "system") {
      speakCount.set(m.participant_id, (speakCount.get(m.participant_id) ?? 0) + 1)
      chars += m.content.length
    }
  }
  const barData = meeting.participants
    .filter((p) => p.id !== "user")
    .map((p) => ({ name: p.name, count: speakCount.get(p.id) ?? 0 }))
  const maxCount = Math.max(1, ...barData.map((d) => d.count))

  return (
    <div className="space-y-4">
      <Card title="ROUND PROGRESS">
        {progress.round && (
          <div className="mb-3 font-mono text-xs text-assist">
            {progress.round.current} / {progress.round.total}
          </div>
        )}
        <div className="space-y-2">
          {progressSlots.map((slot) => {
            const name = meeting.participants.find((p) => p.id === slot.participantId)?.name ?? slot.participantId
            const avatar = meeting.participants.find((p) => p.id === slot.participantId)?.avatar ?? "•"
            return (
              <div
                key={slot.index}
                className={cn(
                  "flex items-center gap-2 rounded-[10px] px-2 py-1.5 text-xs",
                  slot.state === "current" && "border border-primary/50 bg-primary/10",
                )}
              >
                {slot.state === "done" ? (
                  <Check className="h-3.5 w-3.5 shrink-0 text-[#35d07f]" />
                ) : (
                  <span className="w-3.5 shrink-0 text-center">{avatar}</span>
                )}
                <span className={cn("truncate", slot.state === "pending" && "text-muted-foreground")}>
                  {name}
                </span>
                {slot.state === "current" && (
                  <span className="ml-auto font-mono text-[9px] uppercase tracking-[0.08em] text-primary">
                    进行中
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </Card>

      <Card title="SESSION TELEMETRY">
        <div className="space-y-3 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">消息数</span>
            <span className="font-mono">
              {meeting.messages.filter((m) => m.type !== "system").length}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">讨论字数</span>
            <span className="font-mono">{chars.toLocaleString()}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">连接延迟</span>
            <span className="font-mono">{sseLatencyMs !== null ? `${sseLatencyMs}ms` : "—"}</span>
          </div>
        </div>
        <div className="mt-4 flex h-14 items-end gap-1.5">
          {barData.map((d) => (
            <div
              key={d.name}
              title={`${d.name} · ${d.count}`}
              className="flex-1 rounded-t-[3px] bg-chart-1/70"
              style={{ height: `${Math.max(6, (d.count / maxCount) * 100)}%` }}
            />
          ))}
        </div>
      </Card>
    </div>
  )
}
