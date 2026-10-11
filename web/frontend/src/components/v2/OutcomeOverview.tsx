import { Check, FileCheck2, Vote } from "lucide-react"
import type { BallotT, CommitteeVoteT, OutcomeT } from "@/lib/v2api"
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

const SPLIT_LABELS: Record<CommitteeVoteT["split"], string> = {
  unanimous: "全票一致",
  majority: "多数意见",
  split: "意见分裂",
}

const VERDICT_LABELS: Record<BallotT["verdict"], string> = {
  approve: "赞成",
  adjust: "调整",
  reject: "反对",
  abstain: "弃权",
}

export function CommitteeVoteCard({ vote }: { vote: CommitteeVoteT }) {
  const quorum = vote.quorum
  const tally = vote.tally ?? {}
  const pct = (key: string) => (quorum > 0 ? Math.round(((tally[key] ?? 0) / quorum) * 100) : 0)

  return (
    <div className="flex flex-col gap-3 rounded-[14px] border border-border bg-panel p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Vote className="size-[18px] text-primary" aria-hidden />
          委员会投票
        </span>
        <span className="flex items-center gap-2">
          <span className="rounded-lg bg-accent px-[9px] py-[3px] text-xs font-medium text-primary">
            {SPLIT_LABELS[vote.split]}
          </span>
          <span className="rounded-md bg-card px-2 py-0.5 text-xs text-muted-foreground">匿名</span>
        </span>
      </div>
      <div
        className="flex h-2 overflow-hidden rounded-full bg-border"
        role="img"
        aria-label={`委员会投票：赞成 ${tally.approve ?? 0}，调整 ${tally.adjust ?? 0}，反对 ${tally.reject ?? 0}`}
      >
        <span className="bg-emerald-500" style={{ width: `${pct("approve")}%` }} />
        <span className="bg-amber-500" style={{ width: `${pct("adjust")}%` }} />
        <span className="bg-rose-500" style={{ width: `${pct("reject")}%` }} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>赞成 {tally.approve ?? 0}</span>
        <span>调整 {tally.adjust ?? 0}</span>
        <span>反对 {tally.reject ?? 0}</span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {(vote.ballots ?? []).map((ballot, index) => (
          <li
            key={index}
            className="rounded-[10px] border border-border bg-card px-3 py-2 text-[13px] leading-[1.7] text-secondary-foreground"
          >
            {`评审 ${index + 1}：${VERDICT_LABELS[ballot.verdict] ?? ballot.verdict}${
              ballot.verdict === "abstain" ? "" : `（信心 ${ballot.confidence}/5）`
            }${ballot.reason ? `—— ${ballot.reason}` : ""}`}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function OutcomeOverview({
  outcome,
  committeeVote = null,
  confirmedText,
  confirmedSeq,
  confirming,
  onConfirm,
}: {
  outcome: OutcomeT
  committeeVote?: CommitteeVoteT | null
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
      {committeeVote && committeeVote.quorum > 0 ? <CommitteeVoteCard vote={committeeVote} /> : null}
    </section>
  )
}
