import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"
import type { Participant } from "@/types"

function StatusText({ status }: { status: Participant["status"] }) {
  if (status === "thinking") {
    return (
      <span className="flex items-center gap-1 text-blue-500">
        思考中
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-blue-500" />
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-blue-500" />
        <span className="thinking-dot inline-block h-1 w-1 rounded-full bg-blue-500" />
      </span>
    )
  }
  return (
    <span className={cn(status === "speaking" ? "text-green-600 dark:text-green-400" : "text-muted-foreground")}>
      {status === "speaking" ? "发言中" : "等待中"}
    </span>
  )
}

export function ParticipantBar({ participants }: { participants: Participant[] }) {
  return (
    <div className="border-b bg-muted/40 px-6 py-2">
      <div className="mx-auto flex max-w-4xl flex-wrap gap-2">
        {participants.map((p) => (
          <div
            key={p.id}
            className="flex items-center gap-2 rounded-full border bg-card py-1 pl-1 pr-3 shadow-sm"
          >
            <Avatar className="h-7 w-7 rounded-full border">
              <AvatarFallback className="text-sm">{p.avatar}</AvatarFallback>
            </Avatar>
            <div className="text-xs leading-tight">
              <div className="font-medium">{p.name}</div>
              <StatusText status={p.status} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
