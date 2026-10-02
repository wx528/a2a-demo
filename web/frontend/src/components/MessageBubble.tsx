import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { MarkdownContent } from "@/components/MarkdownContent"
import { cn } from "@/lib/utils"
import type { ChatMessage, Participant } from "@/types"

export function MessageBubble({ msg, participants }: { msg: ChatMessage; participants: Participant[] }) {
  const isUser = msg.participant_id === "user"
  const isSystem = msg.participant_id === "system"
  const isJudge = msg.type === "judge"
  const avatar =
    participants.find((p) => p.id === msg.participant_id)?.avatar || (isSystem ? "🔔" : "💬")

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex max-w-[85%] gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
        <Avatar className="mt-1 h-9 w-9 rounded-lg border bg-background">
          <AvatarFallback className="rounded-lg text-lg">{avatar}</AvatarFallback>
        </Avatar>
        <div
          className={cn(
            "min-w-0 rounded-2xl px-4 py-3 text-sm",
            isUser && "bg-primary text-primary-foreground",
            isSystem && "border bg-muted text-muted-foreground",
            isJudge && "border-2 border-amber-500/60 bg-amber-500/5 shadow-sm",
            !isUser && !isSystem && !isJudge && "border bg-card",
          )}
        >
          <div className="mb-1 flex items-center gap-2 text-xs opacity-75">
            <span className="font-medium">{msg.participant_name}</span>
            <span>{msg.timestamp}</span>
            {isJudge && (
              <Badge variant="outline" className="border-amber-500/60 text-amber-600 dark:text-amber-400">
                裁判总结
              </Badge>
            )}
          </div>
          {isUser || isSystem ? (
            <div className="whitespace-pre-wrap break-words">{msg.content}</div>
          ) : (
            <MarkdownContent content={msg.content} />
          )}
        </div>
      </div>
    </div>
  )
}
