import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Eyebrow } from "@/components/Eyebrow"
import { cn } from "@/lib/utils"
import type { Participant } from "@/types"

function StatusText({ status, phase }: { status: Participant["status"]; phase?: string }) {
  if (status === "thinking") {
    return (
      <span className="flex items-center gap-1 text-primary">
        {phase ?? "思考中"}
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-primary" />
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-primary" />
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-primary" />
      </span>
    )
  }
  return (
    <span
      className={cn(
        status === "speaking" ? "text-[#35d07f]" : "text-muted-foreground",
      )}
    >
      {status === "speaking" ? "发言中" : "等待中"}
    </span>
  )
}

export function ParticipantBar({ participants }: { participants: Participant[] }) {
  return (
    <div className="border-b bg-card/40 px-6 py-2.5">
      <div className="flex items-center gap-3">
        <Eyebrow>AGENTS · {participants.length}</Eyebrow>
        <div className="flex flex-wrap items-center gap-2">
          {participants.map((p) => (
            <div
              key={p.id}
              className="flex items-center gap-2 rounded-full border bg-card py-1 pl-1 pr-3"
            >
              <Avatar className="h-6 w-6 rounded-full border">
                <AvatarFallback className="text-xs">{p.avatar}</AvatarFallback>
              </Avatar>
              <span className="text-xs font-medium">{p.name}</span>
              <span className="text-[11px] leading-none">
                <StatusText status={p.status} phase={p.phase} />
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
