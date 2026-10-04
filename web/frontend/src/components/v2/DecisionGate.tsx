import { useRef, useState } from "react"
import type { KeyboardEvent } from "react"
import { CircleHelp, Check, Loader2 } from "lucide-react"
import { toast } from "sonner"
import type { V2StreamTaskT } from "@/hooks/useV2Stream"
import { submitDecision, type DecisionT, type V2TaskT } from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

export function DecisionGate({
  task,
  decision,
  onDecided,
}: {
  task: V2StreamTaskT
  decision: DecisionT
  onDecided: (updated: V2TaskT, uncertain: boolean) => void
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([])

  const recommended = decision.options.find((option) => option.recommended)

  const focusOption = (index: number) => {
    const count = decision.options.length
    const next = (index + count) % count
    const option = decision.options[next]
    setSelectedId(option.id)
    optionRefs.current[next]?.focus()
  }

  const handleGroupKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = decision.options.findIndex((option) => option.id === selectedId)
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault()
      focusOption(index < 0 ? 0 : index + 1)
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault()
      focusOption(index < 0 ? decision.options.length - 1 : index - 1)
    }
  }

  const confirm = async () => {
    if (!selectedId || submitting) return
    setSubmitting(true)
    try {
      const updated = await submitDecision(task.id, decision.id, selectedId)
      const uncertain =
        decision.options.find((option) => option.id === selectedId)?.uncertain ?? false
      onDecided(updated, uncertain)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "提交失败，请重试")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section
      aria-label="关键决策确认"
      className="flex flex-col gap-4 rounded-[14px] border border-accent-border bg-accent p-[22px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <CircleHelp className="size-[18px] text-primary" aria-hidden />
          <span className="text-[13px] font-bold text-primary">需要你确认</span>
        </div>
        <span className="text-xs text-muted-foreground">普通发言已停止，等待你的选择</span>
      </div>
      <h3 className="text-xl font-bold text-foreground">{decision.question}</h3>
      {recommended ? (
        <p className="text-sm text-secondary-foreground">
          基于你的约束，建议选择「{recommended.label}」。这是建议，尚未替你确认。
        </p>
      ) : null}
      <div
        role="radiogroup"
        aria-label={decision.question}
        onKeyDown={handleGroupKeyDown}
        className="flex flex-col gap-2.5 sm:flex-row"
      >
        {decision.options.map((option, index) => {
          const selected = option.id === selectedId
          return (
            <button
              key={option.id}
              ref={(el) => {
                optionRefs.current[index] = el
              }}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={submitting}
              onClick={() => setSelectedId(option.id)}
              className={cn(
                "flex flex-1 flex-col gap-2.5 rounded-[10px] border bg-card p-3.5 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:pointer-events-none",
                selected
                  ? "border-primary bg-accent/50 ring-2 ring-primary/30"
                  : "border-border hover:border-primary/40",
              )}
            >
              <span className="flex items-center gap-2">
                <span
                  aria-hidden
                  className={cn(
                    "flex size-4 items-center justify-center rounded-full border-2",
                    selected ? "border-primary bg-primary" : "border-muted-foreground/40",
                  )}
                >
                  {selected ? <Check className="size-3 text-primary-foreground" /> : null}
                </span>
                {option.recommended ? (
                  <span className="rounded-lg bg-accent px-[9px] py-[3px] text-xs text-primary">
                    建议
                  </span>
                ) : null}
              </span>
              <span className="text-sm font-bold text-foreground">{option.label}</span>
              <span className="text-xs text-muted-foreground">{option.impact}</span>
            </button>
          )
        })}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="min-w-0 text-[13px] text-secondary-foreground">
          请选择一项。确认后，方案设计师将按新边界修订试点路径，再进入「形成建议」。
        </p>
        <button
          type="button"
          disabled={!selectedId || submitting}
          onClick={() => void confirm()}
          className={cn(
            "flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-primary px-[18px] text-sm font-bold text-primary-foreground transition-colors disabled:pointer-events-none disabled:opacity-50",
            FOCUS_RING,
          )}
        >
          {submitting ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden />
              已确认，讨论继续中
            </>
          ) : (
            "确认选择"
          )}
        </button>
      </div>
    </section>
  )
}
