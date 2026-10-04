import { CircleCheck, Columns2, FileCheck2, ScanSearch, Signpost } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

interface GoalCardT {
  type: string
  icon: LucideIcon
  title: string
  desc: string
}

const GOAL_CARDS: GoalCardT[] = [
  { type: "research", icon: ScanSearch, title: "研究问题", desc: "厘清事实与知识边界" },
  { type: "compare", icon: Columns2, title: "比较方案", desc: "看清差异与取舍" },
  { type: "review", icon: FileCheck2, title: "评审内容", desc: "发现盲点与改进方向" },
  { type: "decision", icon: Signpost, title: "做出决策", desc: "形成建议与下一步" },
]

export function GoalCards({
  selected,
  onSelect,
}: {
  selected: string
  onSelect: (t: string) => void
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {GOAL_CARDS.map((card) => {
        const isSelected = card.type === selected
        const Icon = card.icon
        return (
          <button
            key={card.type}
            type="button"
            aria-pressed={isSelected}
            onClick={() => {
              if (card.type !== "decision") {
                onSelect("decision")
                toast.info("该目标类型本轮暂不支持，已为你锁定「做出决策」路径")
                return
              }
              onSelect(card.type)
            }}
            className={cn(
              "relative flex cursor-pointer flex-col gap-2.5 rounded-[14px] border p-[18px] text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              isSelected
                ? "border-primary bg-accent"
                : "border-border bg-card hover:border-primary/40",
            )}
          >
            <Icon
              className={cn("size-[22px]", isSelected ? "text-primary" : "text-muted-foreground")}
              aria-hidden
            />
            <span className={cn("text-base font-bold", isSelected ? "text-primary" : "text-foreground")}>
              {card.title}
            </span>
            <span className="text-[13px] text-muted-foreground">{card.desc}</span>
            {isSelected && (
              <CircleCheck className="absolute top-[18px] right-[18px] size-[18px] text-primary" aria-hidden />
            )}
          </button>
        )
      })}
    </div>
  )
}
