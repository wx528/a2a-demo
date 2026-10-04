import { useEffect, useRef, useState } from "react"
import type { KeyboardEvent } from "react"
import { ArrowUp, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { sendIntervention, type InterventionIntentT, type TaskStatusT } from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

const INTENTS: InterventionIntentT[] = ["追问", "补充条件", "调整方向"]

export function InterventionBar({
  taskId,
  status,
  disabled = false,
  prefill = "",
}: {
  taskId: string
  status?: TaskStatusT
  disabled?: boolean
  prefill?: string
}) {
  const [intent, setIntent] = useState<InterventionIntentT | null>(null)
  const [text, setText] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [ackVisible, setAckVisible] = useState(false)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const ackTimerRef = useRef<number | null>(null)

  useEffect(() => {
    if (prefill) {
      setText(prefill)
      inputRef.current?.focus()
    }
  }, [prefill])

  useEffect(
    () => () => {
      if (ackTimerRef.current !== null) window.clearTimeout(ackTimerRef.current)
    },
    [],
  )

  const showAck = () => {
    setAckVisible(true)
    if (ackTimerRef.current !== null) window.clearTimeout(ackTimerRef.current)
    ackTimerRef.current = window.setTimeout(() => setAckVisible(false), 8000)
  }

  const submit = async () => {
    const value = text.trim()
    if (!value || submitting || disabled) return
    setSubmitting(true)
    try {
      await sendIntervention(taskId, intent ?? "追问", value)
      setText("")
      setIntent(null)
      showAck()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "发送失败，请重试")
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void submit()
    }
  }

  const waiting = status === "waiting_confirmation"

  return (
    <section
      aria-label="介入输入"
      className="flex flex-col gap-4 rounded-[14px] border border-border bg-card p-[18px]"
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="text-xs text-muted-foreground">介入意图 · 可选</span>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="介入意图">
          {INTENTS.map((item) => {
            const selected = intent === item
            return (
              <button
                key={item}
                type="button"
                aria-pressed={selected}
                disabled={disabled}
                onClick={() => setIntent((prev) => (prev === item ? null : item))}
                className={cn(
                  "rounded-lg border px-[9px] py-[3px] text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
                  selected
                    ? "border-accent-border bg-accent text-primary"
                    : "border-transparent bg-panel text-secondary-foreground hover:text-foreground",
                )}
              >
                {item}
              </button>
            )
          })}
        </div>
      </div>
      <div className="flex h-12 items-center gap-3 rounded-lg border border-border bg-background px-4 transition focus-within:ring-2 focus-within:ring-ring">
        <input
          ref={inputRef}
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="补充约束，或告诉大家接下来该讨论什么…"
          aria-label="补充约束，或告诉大家接下来该讨论什么"
          className="min-w-0 flex-1 bg-transparent text-[15px] text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-50"
        />
        <button
          type="button"
          disabled={disabled || !text.trim() || submitting}
          onClick={() => void submit()}
          className={cn(
            "flex h-9 shrink-0 items-center gap-2 rounded-lg bg-primary px-3 text-[13px] font-bold text-primary-foreground transition-colors disabled:pointer-events-none disabled:opacity-50",
            FOCUS_RING,
          )}
        >
          {submitting ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <ArrowUp className="size-4" aria-hidden />
          )}
          发送
        </button>
      </div>
      <p aria-live="polite" className="min-h-[16px] text-xs text-success">
        {ackVisible ? (
          <>
            已接收 · 将在当前发言结束后处理
            {waiting ? " · 当前在等待你的关键选择" : null}
          </>
        ) : null}
      </p>
      <p className="text-xs text-muted-foreground">
        补充内容会加入讨论；关键选择仍需在上方确认。
      </p>
    </section>
  )
}
