import { useState } from "react"
import { ChevronDown, SlidersHorizontal } from "lucide-react"
import type { AdvancedModeT } from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

const MODES: { value: AdvancedModeT; label: string }[] = [
  { value: "pipeline", label: "流水线" },
  { value: "roundtable", label: "圆桌" },
  { value: "debate", label: "辩论" },
]

export function AdvancedSettings({
  mode,
  rounds,
  onMode,
  onRounds,
}: {
  mode: AdvancedModeT
  rounds: number
  onMode: (mode: AdvancedModeT) => void
  onRounds: (rounds: number) => void
}) {
  const [open, setOpen] = useState(false)
  const debateLocked = mode === "debate" && rounds > 1

  return (
    <section aria-label="高级设置">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "flex w-full items-center justify-between gap-3 border-y border-border py-4 text-left",
          FOCUS_RING,
        )}
      >
        <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <SlidersHorizontal className="size-[17px] shrink-0 text-muted-foreground" aria-hidden />
          <span className="text-sm font-medium text-foreground">高级设置</span>
          <span className="text-[13px] text-muted-foreground">
            讨论模式（流水线 / 圆桌 / 辩论）与轮数
          </span>
        </span>
        <ChevronDown
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3 pt-4">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span className="text-sm text-muted-foreground">讨论模式</span>
            <div role="radiogroup" aria-label="讨论模式" className="flex flex-wrap items-center gap-4">
              {MODES.map((option) => (
                <label key={option.value} className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
                  <input
                    type="radio"
                    name="v2-advanced-mode"
                    value={option.value}
                    checked={mode === option.value}
                    onChange={() => onMode(option.value)}
                    className={cn("size-4 rounded-full accent-primary", FOCUS_RING)}
                  />
                  {option.label}
                </label>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            轮数
            <select
              value={rounds}
              disabled={debateLocked}
              onChange={(event) => onRounds(Number(event.target.value))}
              className={cn(
                "h-9 rounded-lg border border-border bg-card px-2.5 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              {[1, 2, 3].map((count) => (
                <option key={count} value={count}>
                  {count}
                </option>
              ))}
            </select>
          </label>
          {debateLocked ? (
            <p className="text-xs text-destructive" role="note">
              辩论模式本轮仅支持 1 轮
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
