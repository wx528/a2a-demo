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
    <footer className="border-t bg-card p-4">
      <div className="mx-auto flex max-w-4xl items-end gap-3">
        <Textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="继续提问或追加需求...（Enter 发送，Shift+Enter 换行）"
          rows={1}
          className="max-h-40 min-h-11 resize-none"
        />
        <Button
          size="icon"
          className="h-11 w-11 shrink-0"
          onClick={() => void send()}
          disabled={sending || !value.trim()}
        >
          {sending ? <Loader2 className="animate-spin" /> : <SendHorizontal />}
        </Button>
      </div>
    </footer>
  )
}
