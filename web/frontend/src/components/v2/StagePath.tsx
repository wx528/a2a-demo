import { ArrowRight } from "lucide-react"
import { cn } from "@/lib/utils"

const STAGES = [
  {
    num: "01",
    title: "澄清需求",
    desc: "明确协作场景与约束",
    foot: "厘清现状",
    highlight: false,
  },
  {
    num: "02",
    title: "比较方案",
    desc: "保持现状与试点的取舍",
    foot: "探索路径",
    highlight: false,
  },
  {
    num: "03",
    title: "评审风险",
    desc: "风险清单与待验证项",
    foot: "关键节点请你确认",
    highlight: true,
  },
  {
    num: "04",
    title: "形成建议",
    desc: "采用建议与试点计划",
    foot: "沉淀成果",
    highlight: false,
  },
]

export function StagePath() {
  return (
    <section className="flex flex-col gap-4" aria-label="讨论阶段">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-bold text-foreground">讨论如何走向成果</h3>
        <span className="text-[13px] text-muted-foreground">
          普通发言自动推进 · 关键节点由你确认
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {STAGES.map((stage, index) => (
          <div
            key={stage.num}
            className={cn(
              "flex flex-col gap-2 rounded-xl border p-[18px]",
              stage.highlight
                ? "border-accent-border bg-accent"
                : "border-border bg-card",
            )}
          >
            <div className="flex items-center justify-between">
              <span
                className={cn(
                  "font-mono text-[13px]",
                  stage.highlight ? "text-primary" : "text-success",
                )}
              >
                {stage.num}
              </span>
              {index < STAGES.length - 1 ? (
                <ArrowRight className="size-4 text-muted-foreground" aria-hidden />
              ) : null}
            </div>
            <span className="text-base font-bold text-foreground">{stage.title}</span>
            <span className="text-sm text-secondary-foreground">{stage.desc}</span>
            <span
              className={cn(
                "text-xs",
                stage.highlight ? "text-primary" : "text-muted-foreground",
              )}
            >
              {stage.foot}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
