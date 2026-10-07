import type { ExpertT } from "@/lib/v2api"
import {
  PURPOSES,
  PURPOSE_DUTIES,
  PURPOSE_LABELS,
  PURPOSE_TAG_BY,
} from "@/lib/purposes"
import { cn } from "@/lib/utils"

const FOCUS_RING =
  "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

export function PurposeSlots({
  assignments,
  experts,
  demo,
  onAssign,
  onManage,
}: {
  assignments: Record<string, string>
  experts: ExpertT[]
  demo: boolean
  onAssign: (purpose: string, expertId: string) => void
  onManage: () => void
}) {
  const byId = new Map(experts.map((expert) => [expert.id, expert]))
  const enabled = experts.filter((expert) => expert.enabled)
  return (
    <div className="flex flex-col">
      {PURPOSES.map((purpose) => {
        const assignedId = assignments[purpose] ?? ""
        const assigned = byId.get(assignedId)
        const matched = enabled.filter((expert) =>
          expert.tags.includes(PURPOSE_TAG_BY[purpose] ?? ""),
        )
        const rest = enabled.filter(
          (expert) => !expert.tags.includes(PURPOSE_TAG_BY[purpose] ?? ""),
        )
        return (
          <div
            key={purpose}
            className="flex items-center gap-4 border-b border-border py-3"
          >
            <div
              className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-panel text-[23px]"
              aria-hidden
            >
              {assigned?.emoji ?? "🔌"}
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-[15px] font-bold text-foreground">
                {PURPOSE_LABELS[purpose]}
              </span>
              <span className="text-xs text-muted-foreground">
                {PURPOSE_DUTIES[purpose]}
              </span>
            </div>
            <select
              value={assignedId}
              disabled={demo}
              aria-label={`${PURPOSE_LABELS[purpose]}指派专家`}
              onChange={(event) => onAssign(purpose, event.target.value)}
              className={cn(
                "shrink-0 rounded-lg border border-border bg-card px-2 py-1.5 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring",
                demo && "cursor-not-allowed opacity-60",
              )}
            >
              {matched.length > 0 ? (
                <optgroup label="标签匹配">
                  {matched.map((expert) => (
                    <option key={expert.id} value={expert.id}>
                      {expert.emoji} {expert.name}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              {rest.length > 0 ? (
                <optgroup label="全部专家">
                  {rest.map((expert) => (
                    <option key={expert.id} value={expert.id}>
                      {expert.emoji} {expert.name}
                    </option>
                  ))}
                </optgroup>
              ) : null}
            </select>
          </div>
        )
      })}
      {demo ? (
        <div
          role="note"
          className="mt-3 flex items-start gap-2.5 rounded-[10px] bg-warning-bg p-3.5"
        >
          <p className="text-xs text-warning">演示模式使用内置专家脚本</p>
        </div>
      ) : null}
      <button
        type="button"
        onClick={onManage}
        className={cn(
          "mt-3 self-start rounded-md text-sm text-primary hover:underline",
          FOCUS_RING,
        )}
      >
        ＋ 添加专家
      </button>
    </div>
  )
}
