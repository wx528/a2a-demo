import { useRef, useState, type KeyboardEvent } from "react"
import { Loader2, SendHorizontal } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

export function ChatInput({ onSend }: { onSend: (content: string) => Promise<boolean> }) {
  const [value, setValue] = useState("")
  const [sending, setSending] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)

  const send = async () => {
    const content = value.trim()
    if (!content || sending) return
    setSending(true)
    const ok = await onSend(content)
    setSending(false)
    if (ok) {
      setValue("")
      ref.current?.focus()
    }
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <footer className="border-t bg-card/60 px-6 py-4 backdrop-blur">
      <div className="mx-auto max-w-3xl">
        <div className="relative">
          <Textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="输入你的观点或质询..."
            rows={1}
            className="max-h-40 min-h-14 resize-none rounded-[24px] pr-16"
          />
          <Button
            size="icon"
            className="absolute bottom-2 right-2 h-10 w-10 rounded-full shadow-glow"
            onClick={() => void send()}
            disabled={sending || !value.trim()}
          >
            {sending ? <Loader2 className="animate-spin" /> : <SendHorizontal />}
          </Button>
        </div>
        <div className="mt-2 text-center font-mono text-[9px] uppercase tracking-[0.08em] text-muted-foreground">
          Enter 发送 · Shift+Enter 换行
        </div>
      </div>
    </footer>
  )
}
