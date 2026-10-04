import { useState } from "react"
import { ArrowRight, Check, Paperclip, X } from "lucide-react"
import { toast } from "sonner"
import { createTask, type MaterialT } from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

export function TaskCreateCard({ onCreated }: { onCreated: (id: string) => void }) {
  const [goalText, setGoalText] = useState("")
  const [constraints, setConstraints] = useState<string[]>([])
  const [constraintDraft, setConstraintDraft] = useState("")
  const [materials, setMaterials] = useState<MaterialT[]>([])
  const [materialName, setMaterialName] = useState("")
  const [materialText, setMaterialText] = useState("")
  const [materialOpen, setMaterialOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const hasGoal = goalText.trim().length > 0

  const addConstraint = () => {
    const text = constraintDraft.trim()
    if (!text) return
    setConstraints((prev) => [...prev, text])
    setConstraintDraft("")
  }

  const addMaterial = () => {
    const name = materialName.trim()
    const text = materialText.trim()
    if (!name || !text) {
      toast.info("请填写材料名并粘贴文本")
      return
    }
    setMaterials((prev) => [...prev, { name, text }])
    setMaterialName("")
    setMaterialText("")
    setMaterialOpen(false)
  }

  const submit = async () => {
    if (!hasGoal) {
      toast.info("先填写你要做的判断")
      return
    }
    if (submitting) return
    setSubmitting(true)
    try {
      const task = await createTask({
        goal_type: "decision",
        goal_text: goalText.trim(),
        expected_outcome: "",
        constraints,
        materials,
      })
      sessionStorage.setItem("v2DraftTask", task.id)
      onCreated(task.id)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "创建任务失败，请重试")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="flex flex-col gap-5 rounded-[20px] border-[1.5px] border-accent-border bg-card p-6 shadow-page">
      <h2 className="text-sm font-bold text-foreground">你想做出什么判断？</h2>
      <textarea
        value={goalText}
        onChange={(event) => setGoalText(event.target.value)}
        placeholder="例如：团队是否需要引入 A2A？什么场景值得先试点？"
        aria-label="你想做出什么判断"
        className="min-h-[96px] w-full resize-none bg-transparent text-[19px] text-foreground outline-none placeholder:text-muted-foreground"
      />
      <p className="text-sm text-muted-foreground">
        也可以写下已有方案、必须满足的条件，或还不确定的地方。
      </p>
      <div className="flex flex-col gap-2">
        <span className="text-xs text-muted-foreground">上下文约束（可选）</span>
        {constraints.map((constraint, index) => (
          <div
            key={`${constraint}-${index}`}
            className="group flex items-center gap-2 text-sm text-foreground"
          >
            <Check className="size-4 shrink-0 text-primary" aria-hidden />
            <span className="min-w-0 flex-1 break-words">{constraint}</span>
            <button
              type="button"
              aria-label={`删除约束 ${constraint}`}
              onClick={() => setConstraints((prev) => prev.filter((_, i) => i !== index))}
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              )}
            >
              <X className="size-3.5" aria-hidden />
            </button>
          </div>
        ))}
        <input
          value={constraintDraft}
          onChange={(event) => setConstraintDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault()
              addConstraint()
            }
          }}
          placeholder="＋ 添加约束"
          aria-label="添加约束"
          className={cn(
            "h-9 w-full rounded-lg bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring",
          )}
        />
      </div>
      <hr className="border-border" />
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Paperclip className="size-[18px] shrink-0 text-primary" aria-hidden />
            <button
              type="button"
              aria-expanded={materialOpen}
              onClick={() => setMaterialOpen((prev) => !prev)}
              className={cn("rounded-sm text-sm font-medium text-primary hover:underline", FOCUS_RING)}
            >
              添加材料
            </button>
            <span className="text-xs text-muted-foreground">文档、链接或粘贴文本 · 可选</span>
          </div>
          {materialOpen && (
            <div className="flex flex-col gap-2 rounded-[10px] border border-border bg-background p-3">
              <input
                value={materialName}
                onChange={(event) => setMaterialName(event.target.value)}
                placeholder="材料名"
                aria-label="材料名"
                className={cn(
                  "h-9 w-full rounded-lg border border-border bg-card px-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring",
                )}
              />
              <textarea
                value={materialText}
                onChange={(event) => setMaterialText(event.target.value)}
                placeholder="粘贴文本"
                aria-label="粘贴文本"
                className={cn(
                  "min-h-[72px] w-full resize-none rounded-lg border border-border bg-card p-2.5 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring",
                )}
              />
              <button
                type="button"
                onClick={addMaterial}
                className={cn(
                  "h-8 self-start rounded-lg bg-primary px-3 text-xs font-bold text-primary-foreground transition-colors hover:bg-primary/90",
                  FOCUS_RING,
                )}
              >
                添加
              </button>
            </div>
          )}
          {materials.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <div className="flex flex-wrap gap-1.5">
                {materials.map((material, index) => (
                  <span
                    key={`${material.name}-${index}`}
                    className="inline-flex items-center gap-1 rounded-lg bg-panel px-2 py-1 text-xs text-foreground"
                  >
                    {material.name}
                    <button
                      type="button"
                      aria-label={`移除材料 ${material.name}`}
                      onClick={() => setMaterials((prev) => prev.filter((_, i) => i !== index))}
                      className={cn(
                        "flex size-4 items-center justify-center rounded-sm text-muted-foreground hover:text-destructive",
                        FOCUS_RING,
                      )}
                    >
                      <X className="size-3" aria-hidden />
                    </button>
                  </span>
                ))}
              </div>
              <span className="text-xs text-muted-foreground">仅登记文本，不做文档解析</span>
            </div>
          )}
        </div>
        <button
          type="button"
          title={hasGoal ? undefined : "先填写你要做的判断"}
          aria-disabled={!hasGoal || submitting}
          onClick={() => void submit()}
          className={cn(
            "flex h-11 items-center gap-2 rounded-lg px-[18px] text-sm font-bold text-primary-foreground transition-colors",
            hasGoal && !submitting
              ? "bg-primary hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              : "cursor-not-allowed bg-primary/50",
          )}
        >
          {submitting ? "正在创建…" : "生成协作计划"}
          <ArrowRight className="size-4" aria-hidden />
        </button>
      </div>
    </section>
  )
}
