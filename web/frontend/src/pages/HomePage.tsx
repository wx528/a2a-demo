import { useState } from "react"
import { Sparkles } from "lucide-react"
import { GoalCards } from "@/components/v2/GoalCards"
import { RecentTasks } from "@/components/v2/RecentTasks"
import { Shell } from "@/components/v2/Shell"
import { TaskCreateCard } from "@/components/v2/TaskCreateCard"
import { ThemeToggle } from "@/components/v2/ThemeToggle"
import { useHashRoute } from "@/lib/router"

export function HomePage() {
  const { navigate } = useHashRoute()
  const [selected, setSelected] = useState("decision")

  return (
    <Shell
      title="开始一个有目标的协作"
      subtitle="先定义你要解决的问题，再决定如何讨论"
      topRight={
        <div className="flex items-center gap-3">
          <span className="rounded-lg bg-success-bg px-[9px] py-[3px] text-xs text-success">
            团队私有工作区
          </span>
          <ThemeToggle />
        </div>
      }
    >
      <div className="flex w-full max-w-[1200px] flex-col gap-8 px-[64px] py-12">
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Sparkles className="size-[18px] text-primary" aria-hidden />
            <span className="text-[13px] font-bold text-primary">不同视角，帮助你完成判断</span>
          </div>
          <h1 className="text-[38px] leading-[1.3] font-bold text-foreground">
            这次，你想弄清什么？
          </h1>
          <p className="text-base text-secondary-foreground">
            把问题、背景和顾虑放在一起。AI 会整理讨论计划，在关键节点邀请你参与。
          </p>
        </div>
        <GoalCards selected={selected} onSelect={setSelected} />
        <TaskCreateCard onCreated={() => navigate("#/plan")} />
        <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
          <span className="text-muted-foreground">提出目标 → 确认计划 → 关键节点介入 → 获得成果</span>
          <span className="text-secondary-foreground">计划确认后才会开始讨论</span>
        </div>
        <RecentTasks />
      </div>
    </Shell>
  )
}
