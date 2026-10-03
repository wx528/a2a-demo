import { useEffect, useRef, useState } from "react"
import { ArrowDown } from "lucide-react"
import { Button } from "@/components/ui/button"
import { MessageBubble } from "@/components/MessageBubble"
import { buildProgress } from "@/lib/sequence"
import { roleTagFor } from "@/lib/labels"
import type { Meeting } from "@/types"

export function MessageList({ meeting }: { meeting: Meeting }) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [atBottom, setAtBottom] = useState(true)

  const progress = buildProgress(meeting)
  const judgeRound = progress.round ? progress.round.current : null

  const lastLen = meeting.messages[meeting.messages.length - 1]?.content.length ?? 0

  useEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [meeting.messages.length, lastLen, atBottom])

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80)
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={scrollRef} onScroll={handleScroll} className="h-full overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-3xl space-y-4">
          {meeting.messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              msg={msg}
              participants={meeting.participants}
              roleTag={roleTagFor(meeting, msg.participant_id)}
              judgeRound={msg.type === "judge" ? judgeRound : null}
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
      {!atBottom && (
        <Button
          size="icon"
          className="absolute bottom-4 right-6 rounded-full shadow-glow"
          onClick={() => {
            setAtBottom(true)
            bottomRef.current?.scrollIntoView({ behavior: "smooth" })
          }}
        >
          <ArrowDown />
        </Button>
      )}
    </div>
  )
}
