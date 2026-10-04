import { STAGE_LABELS, STAGE_ORDER } from "@/lib/roles"
import { cn } from "@/lib/utils"

type StageNameT = (typeof STAGE_ORDER)[number]

export function StageTimeline({ current }: { current: string }) {
  const currentIndex = STAGE_ORDER.indexOf(current as StageNameT)
  return (
    <div className="flex gap-2.5">
      {STAGE_ORDER.map((stage, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "future"
        const label = STAGE_LABELS[stage] ?? stage
        return (
          <span
            key={stage}
            aria-current={state === "current" ? "step" : undefined}
            className={cn(
              "flex-1 rounded-md py-[7px] text-center text-xs",
              state === "done" && "bg-panel text-success",
              state === "current" && "bg-accent font-bold text-primary",
              state === "future" && "bg-panel text-muted-foreground",
            )}
          >
            {state === "done" ? `✓ ${label}` : label}
          </span>
        )
      })}
    </div>
  )
}
