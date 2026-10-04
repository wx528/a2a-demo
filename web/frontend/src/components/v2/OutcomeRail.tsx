import { NotebookPen } from "lucide-react"
import type { V2StreamTaskT } from "@/hooks/useV2Stream"
import { useHashRoute } from "@/lib/router"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

const LABEL_CHIPS: Record<string, { text: string; className: string }> = {
  ai_suggestion: { text: "AI 协作建议 · 待团队审批", className: "bg-accent text-primary" },
  draft: { text: "讨论草稿", className: "bg-panel text-muted-foreground" },
  team_confirmed: { text: "团队已确认", className: "bg-success-bg text-success" },
}

interface SummaryItemT {
  text: string
  seq: number | null
}

function dedupe(items: SummaryItemT[]): SummaryItemT[] {
  const seen = new Set<string>()
  const result: SummaryItemT[] = []
  for (const item of items) {
    if (seen.has(item.text)) continue
    seen.add(item.text)
    result.push(item)
  }
  return result
}

export function OutcomeRail({
  task,
  onJumpToTurn,
}: {
  task: V2StreamTaskT
  onJumpToTurn: (seq: number) => void
}) {
  const { navigate } = useHashRoute()
  const outcome = task.outcome

  const findSeq = (text: string): number | null => {
    const turn = task.turns.find(
      (item) =>
        !item.live &&
        item.seq > 0 &&
        (item.title === text || (item.body.length > 0 && item.body.includes(text))),
    )
    return turn ? turn.seq : null
  }

  const confirmed = dedupe([
    ...(outcome?.summary_groups?.confirmed ?? []).map((text) => ({
      text,
      seq: findSeq(text),
    })),
    ...task.constraints
      .filter((constraint) => constraint.confirmed)
      .map((constraint) => ({ text: constraint.text, seq: findSeq(constraint.text) })),
  ]).slice(0, 5)
  const disputed = (outcome?.summary_groups?.disputed ?? []).map((text) => ({
    text,
    seq: findSeq(text),
  }))
  const unverified = dedupe([
    ...(outcome?.summary_groups?.unverified ?? []).map((text) => ({
      text,
      seq: findSeq(text),
    })),
    ...task.turns
      .filter((turn) => turn.verified && turn.title)
      .map((turn) => ({ text: turn.title, seq: turn.seq > 0 ? turn.seq : null })),
  ])

  const labelChip = outcome?.label ? LABEL_CHIPS[outcome.label] : null
  const conclusion = outcome?.conclusion ?? ""
  const draftBody = outcome?.reasons?.[0]?.body || conclusion.slice(0, 80)
  const acceptanceText =
    outcome?.acceptance
      ?.map((item) => item.title)
      .filter((title): title is string => Boolean(title))
      .join(" · ") ?? ""

  const renderItems = (items: SummaryItemT[], emptyPlaceholder: string) =>
    items.length === 0 ? (
      <p className="text-sm text-muted-foreground italic">{emptyPlaceholder}</p>
    ) : (
      items.map((item) => (
        <div key={item.text} className="flex flex-col gap-0.5">
          <p className="text-[15px] text-foreground">{item.text}</p>
          {item.seq !== null ? (
            <button
              type="button"
              onClick={() => onJumpToTurn(item.seq as number)}
              className={cn(
                "self-start text-xs text-success underline underline-offset-2 transition-colors hover:text-success/80",
                FOCUS_RING,
              )}
            >
              关联讨论 #{item.seq}
            </button>
          ) : null}
        </div>
      ))
    )

  return (
    <section
      aria-label="成果草稿"
      className="flex w-full shrink-0 flex-col gap-6 self-start rounded-[14px] border border-border bg-card p-6 xl:w-[336px]"
    >
      <div className="flex flex-col gap-1.5">
        <NotebookPen className="size-20 text-primary" aria-hidden />
        <h2 className="text-lg font-bold text-foreground">成果草稿</h2>
        <p className="text-[13px] text-muted-foreground">随讨论更新 · 尚未形成最终建议</p>
      </div>
      <hr className="border-border" />
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-2.5 border-l-2 border-success pl-3.5">
          <h3 className="text-sm font-bold text-success">已确认</h3>
          {renderItems(confirmed, "讨论推进后自动汇总")}
        </div>
        <div className="flex flex-col gap-2.5 border-l-2 border-primary pl-3.5">
          <h3 className="text-sm font-bold text-primary">仍有分歧</h3>
          {renderItems(disputed, "讨论推进后自动汇总")}
        </div>
        <div className="flex flex-col gap-2.5 border-l-2 border-warning pl-3.5">
          <h3 className="text-sm font-bold text-warning">待验证</h3>
          {renderItems(unverified, "讨论推进后自动汇总")}
        </div>
      </div>
      {outcome ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-foreground">建议草稿</h3>
            {labelChip ? (
              <span
                className={cn(
                  "rounded-lg px-[9px] py-[3px] text-xs font-medium",
                  labelChip.className,
                )}
              >
                {labelChip.text}
              </span>
            ) : null}
          </div>
          {conclusion ? (
            <p className="text-[15px] text-foreground">
              <span className="font-bold">初步建议：</span>
              {conclusion}
            </p>
          ) : null}
          {draftBody ? (
            <p className="text-sm text-secondary-foreground">{draftBody}</p>
          ) : null}
          {acceptanceText ? (
            <div className="flex flex-col gap-1 rounded-lg bg-panel p-3.5 text-[13px]">
              <span className="font-medium text-foreground">预期验证</span>
              <span className="text-secondary-foreground">{acceptanceText}</span>
            </div>
          ) : null}
          <p className="text-xs text-muted-foreground">
            依据：{outcome.evidence?.length ?? 0} 条讨论记录
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2 rounded-[10px] border border-dashed border-border p-4">
          <p className="text-[13px] text-muted-foreground">
            讨论推进后，这里会持续汇总已确认约束、分歧与待验证项，并形成建议草稿。
          </p>
        </div>
      )}
      <hr className="border-border" />
      <div className="flex flex-col gap-2">
        <p className="text-[13px] text-secondary-foreground">
          协作完成后，可在「决策成果」页编辑、复制与导出。
        </p>
        <p className="text-xs text-muted-foreground">
          草稿内容来自本次讨论记录，不是外部资料。
        </p>
        {task.status === "completed" ? (
          <button
            type="button"
            onClick={() => navigate(`#/task/${task.id}/outcome`)}
            className={cn(
              "mt-1 flex h-10 items-center justify-center rounded-lg border border-border bg-card text-sm font-medium text-foreground transition-colors hover:bg-panel",
              FOCUS_RING,
            )}
          >
            查看成果
          </button>
        ) : null}
      </div>
    </section>
  )
}
