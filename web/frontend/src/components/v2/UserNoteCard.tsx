import type { V2TurnT } from "@/hooks/useV2Stream"

export function UserNoteCard({ turn }: { turn: V2TurnT }) {
  if (turn.kind === "decision_record") {
    return (
      <div className="flex items-center justify-between gap-3 rounded-[10px] bg-accent px-4 py-3">
        <p className="min-w-0 text-[15px] font-medium text-primary">{turn.title || "你已确认"}</p>
        <span className="shrink-0 font-mono text-xs text-primary/70">#{turn.seq}</span>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1.5 rounded-[10px] bg-success-bg px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-bold text-success">你 · {turn.intent ?? "补充"}</p>
        <span className="shrink-0 font-mono text-xs text-success/70">#{turn.seq}</span>
      </div>
      {turn.body ? (
        <p className="whitespace-pre-wrap text-[15px] text-foreground">{turn.body}</p>
      ) : null}
    </div>
  )
}
