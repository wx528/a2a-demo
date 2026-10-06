import { Check, FileCheck2 } from "lucide-react"
import type { OutcomeT } from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

export function pad(n: number): string {
  return String(n).padStart(2, "0")
}

const LABEL_CHIPS: Record<string, { text: string; className: string }> = {
  draft: { text: "讨论草稿", className: "bg-panel text-muted-foreground" },
  ai_suggestion: { text: "AI 协作建议 · 待团队审批", className: "bg-accent text-primary" },
  team_confirmed: { text: "团队已确认", className: "bg-success-bg text-success" },
}

export function OutcomeOverview({
  outcome,
  confirmedText,
  confirmedSeq,
  confirming,
  onConfirm,
}: {
  outcome: OutcomeT
  confirmedText: string | null
  confirmedSeq: number | null
  confirming: boolean
  onConfirm: () => void
}) {
  const chip = LABEL_CHIPS[outcome.label ?? "ai_suggestion"] ?? LABEL_CHIPS.ai_suggestion
  const summary =
    outcome.reasons?.[0]?.body || (outcome.summary_groups?.confirmed ?? []).join("；")

  return (
    <section
      aria-label="成果概览"
      className="flex flex-col gap-5 rounded-[20px] border border-border bg-card p-8 shadow-page"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <FileCheck2 className="size-20 shrink-0 text-primary" aria-hidden />
          <span className={cn("rounded-lg px-[9px] py-[3px] text-xs font-medium", chip.className)}>
            {chip.text}
          </span>
          {(outcome.label ?? "ai_suggestion") === "ai_suggestion" ? (
            <button
              type="button"
              disabled={confirming}
              onClick={onConfirm}
              className={cn(
                "text-xs text-primary underline underline-offset-2 transition-colors hover:text-primary/80 disabled:pointer-events-none disabled:opacity-50",
                FOCUS_RING,
              )}
            >
              标记为团队已确认
            </button>
          ) : null}
        </div>
        <span className="text-[13px] text-muted-foreground">采用建议与试点计划</span>
      </div>
      <h1 className="text-[26px] font-bold leading-[1.4] whitespace-pre-line text-foreground xl:text-[32px]">
        {outcome.conclusion || "暂无主结论"}
      </h1>
      {summary ? <p className="text-base text-secondary-foreground">{summary}</p> : null}
      <hr className="border-border" />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span className="flex items-center gap-2 text-sm font-medium text-success">
          <Check className="size-[18px] shrink-0" aria-hidden />
          <span>
            {confirmedText
              ? `你已确认：${confirmedText}${confirmedSeq !== null ? ` · #${pad(confirmedSeq)}` : ""}`
              : "你已确认关键约束"}
          </span>
        </span>
        <span className="text-[13px] text-warning">
          协作已完成，不代表方案已验证或审批通过
        </span>
      </div>
    </section>
  )
}
