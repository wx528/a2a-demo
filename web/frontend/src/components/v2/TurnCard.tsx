import type { V2StreamTaskT, V2TurnT } from "@/hooks/useV2Stream"
import { roleMetaFromTask } from "@/lib/roles"
import { cn } from "@/lib/utils"

export function TurnCard({
  turn,
  task = null,
  highlight = false,
}: {
  turn: V2TurnT
  task?: V2StreamTaskT | null
  highlight?: boolean
}) {
  const meta = roleMetaFromTask(task, turn.author)
  return (
    <article
      data-seq={turn.seq}
      className={cn("flex gap-3 rounded-lg transition", highlight && "ring-2 ring-primary/60")}
    >
      <div
        className="flex size-[34px] shrink-0 items-center justify-center rounded-[10px] bg-panel text-[19px]"
        aria-hidden
      >
        {meta.emoji}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm font-bold text-foreground">
            {meta.zh}
            <span className="ml-1.5 text-[13px] font-normal text-muted-foreground">{meta.en}</span>
          </p>
          <span className="shrink-0 font-mono text-xs text-muted-foreground">
            {turn.live ? "···" : `#${turn.seq}`}
          </span>
        </div>
        {turn.title ? <h3 className="text-base font-bold text-foreground">{turn.title}</h3> : null}
        <p className="whitespace-pre-wrap text-[15px] leading-[1.75] text-secondary-foreground">
          {turn.body}
          {turn.live ? (
            <span className="animate-pulse" aria-hidden>
              ▍
            </span>
          ) : null}
        </p>
        {turn.verified ? (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center rounded-lg bg-warning-bg px-[9px] py-[3px] text-xs font-medium text-warning">
              待验证
            </span>
            <span className="text-xs text-muted-foreground">该结论标记为尚未核实</span>
          </div>
        ) : null}
      </div>
    </article>
  )
}
