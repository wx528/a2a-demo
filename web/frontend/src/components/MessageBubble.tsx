import { Scale } from "lucide-react"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { MarkdownContent } from "@/components/MarkdownContent"
import { cn } from "@/lib/utils"
import type { ChatMessage, Participant } from "@/types"

export function MessageBubble({
  msg,
  participants,
  roleTag,
  judgeRound,
}: {
  msg: ChatMessage
  participants: Participant[]
  roleTag?: string
  judgeRound: number | null
}) {
  const isUser = msg.participant_id === "user"
  const isSystem = msg.participant_id === "system"
  const isJudge = msg.type === "judge"
  const avatar =
    participants.find((p) => p.id === msg.participant_id)?.avatar || (isSystem ? "🔔" : "💬")

  if (isSystem) {
    return (
      <div className="flex items-center gap-3 py-1">
        <div className="h-px flex-1 bg-border" />
        <span className="text-xs text-muted-foreground">🔔 {msg.content}</span>
        <div className="h-px flex-1 bg-border" />
      </div>
    )
  }

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex max-w-[85%] gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
        <Avatar className="mt-1 h-9 w-9 rounded-[10px] border bg-background">
          <AvatarFallback className="rounded-[10px] text-lg">{avatar}</AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2 text-xs">
            <span className="font-bold">{msg.participant_name}</span>
            {roleTag && (
              <span className="rounded-full border px-1.5 py-px font-mono text-[9px] uppercase tracking-[0.08em] text-muted-foreground">
                {roleTag}
              </span>
            )}
            <span className="font-mono text-[10px] text-muted-foreground">{msg.timestamp}</span>
          </div>
          {isUser ? (
            <div className="whitespace-pre-wrap break-words rounded-[14px] rounded-tr-[4px] bg-primary px-4 py-3 text-sm text-primary-foreground">
              {msg.content}
            </div>
          ) : isJudge ? (
            <div className="rounded-[14px] border border-[#f6b84a]/60 bg-[#f6b84a]/[0.07] p-4 shadow-soft">
              <div className="mb-2 flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[#f6b84a]/20 text-[#f6b84a]">
                  <Scale className="h-3.5 w-3.5" />
                </div>
                <span className="text-sm font-bold text-[#f6b84a]">
                  裁判总结{judgeRound !== null ? ` · 第 ${judgeRound} 轮` : ""}
                </span>
                <span className="ml-auto rounded-full border border-[#f6b84a]/60 px-2 py-px font-mono text-[9px] tracking-[0.08em] text-[#f6b84a]">
                  VERDICT
                </span>
              </div>
              <MarkdownContent content={msg.content} />
            </div>
          ) : (
            <div className="rounded-[14px] rounded-tl-[4px] border bg-card px-4 py-3">
              <MarkdownContent content={msg.content} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
