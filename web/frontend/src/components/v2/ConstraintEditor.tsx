import { useEffect, useRef, useState } from "react"
import { Check, X } from "lucide-react"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

export function ConstraintEditor({
  constraints,
  onChange,
}: {
  constraints: string[]
  onChange: (next: string[]) => void
}) {
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (adding) inputRef.current?.focus()
  }, [adding])

  const commitDraft = () => {
    const text = draft.trim()
    if (text) onChange([...constraints, text])
  }

  const closeInput = () => {
    setAdding(false)
    setDraft("")
  }

  return (
    <div className="flex flex-col gap-2">
      {constraints.map((constraint, index) => (
        <div key={`${constraint}-${index}`} className="group flex items-start gap-2">
          <Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden />
          <span className="min-w-0 flex-1 break-words text-sm text-foreground">{constraint}</span>
          <button
            type="button"
            aria-label="删除约束"
            onClick={() => onChange(constraints.filter((_, i) => i !== index))}
            className={cn(
              "flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100 hover:text-destructive focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            )}
          >
            <X className="size-3.5" aria-hidden />
          </button>
        </div>
      ))}
      {adding ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault()
              commitDraft()
              setDraft("")
            } else if (event.key === "Escape") {
              closeInput()
            }
          }}
          onBlur={() => {
            commitDraft()
            closeInput()
          }}
          placeholder="输入约束后回车"
          aria-label="添加约束"
          className={cn(
            "h-9 w-full rounded-lg bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring",
          )}
        />
      ) : (
        <button
          type="button"
          onClick={() => {
            setDraft("")
            setAdding(true)
          }}
          className={cn(
            "self-start rounded-md py-1 text-[13px] text-muted-foreground transition-colors hover:text-primary",
            FOCUS_RING,
          )}
        >
          ＋ 添加约束
        </button>
      )}
    </div>
  )
}
