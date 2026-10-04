import { UserRoundCheck } from "lucide-react"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

const ROLES = [
  {
    emoji: "🧬",
    name: "研究员",
    nameEn: "Ada",
    duty: "核实能力边界",
    desc: "区分 MCP 与 A2A，标记尚未核实的能力。",
  },
  {
    emoji: "🧠",
    name: "方案设计师",
    nameEn: "Turing",
    duty: "提出试点路径",
    desc: "从现有系统出发，设计最小可行协作场景。",
  },
  {
    emoji: "⚡",
    name: "挑战者",
    nameEn: "Linus",
    duty: "检查信任与运维风险",
    desc: "质询身份、工具授权、失败恢复与审计边界。",
  },
  {
    emoji: "⚖️",
    name: "决策助手",
    nameEn: "Sage",
    duty: "整理权衡",
    desc: "汇总共识与分歧，形成建议，不代替你做决定。",
  },
]

export function RoleDuties() {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-bold text-foreground">四个视角，一份可用的判断</h3>
        <button
          type="button"
          onClick={() => toast.info("本轮角色固定为四位，职责可在约束中补充")}
          className={cn("shrink-0 rounded-md text-[13px] text-primary hover:underline", FOCUS_RING)}
        >
          调整分工
        </button>
      </div>
      <p className="pb-2 text-sm text-muted-foreground">
        角色按职责参与，所有建议都将标明共识、分歧与待验证项。
      </p>
      <div className="flex flex-col">
        {ROLES.map((role) => (
          <div key={role.nameEn} className="flex gap-4 border-b border-border py-3">
            <div
              className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-panel text-[23px]"
              aria-hidden
            >
              {role.emoji}
            </div>
            <div className="flex w-[146px] shrink-0 flex-col">
              <span className="text-[15px] font-bold text-foreground">{role.name}</span>
              <span className="font-mono text-[13px] text-muted-foreground">{role.nameEn}</span>
            </div>
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-[15px] font-bold text-foreground">{role.duty}</span>
              <span className="text-sm text-secondary-foreground">{role.desc}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-start gap-2.5 rounded-[10px] bg-success-bg p-3.5">
        <UserRoundCheck className="mt-0.5 size-[18px] shrink-0 text-success" aria-hidden />
        <p className="text-sm text-success">
          你负责关键约束与取舍。AI 负责展开论证、整理权衡，不替代团队审批。
        </p>
      </div>
    </div>
  )
}
