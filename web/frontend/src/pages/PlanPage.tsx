import { useEffect, useState } from "react"
import {
  ArrowLeft,
  ArrowRight,
  ChevronRight,
  FileText,
  Loader2,
} from "lucide-react"
import { toast } from "sonner"
import { AdvancedSettings } from "@/components/v2/AdvancedSettings"
import { ConstraintEditor } from "@/components/v2/ConstraintEditor"
import { ExpertPanel } from "@/components/v2/ExpertPanel"
import { RoleDuties } from "@/components/v2/RoleDuties"
import { Shell } from "@/components/v2/Shell"
import { StagePath } from "@/components/v2/StagePath"
import { ThemeToggle } from "@/components/v2/ThemeToggle"
import { useHashRoute } from "@/lib/router"
import {
  getTask,
  startTask,
  type AdvancedModeT,
  type V2TaskT,
} from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

export function PlanPage() {
  const { navigate } = useHashRoute()
  const [draftId] = useState(() => sessionStorage.getItem("v2DraftTask"))
  const [task, setTask] = useState<V2TaskT | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [constraints, setConstraints] = useState<string[]>([])
  const [seededConstraints, setSeededConstraints] = useState<string[]>([])
  const [mode, setMode] = useState<AdvancedModeT>("pipeline")
  const [rounds, setRounds] = useState(2)
  const [starting, setStarting] = useState(false)
  const [expertPanelOpen, setExpertPanelOpen] = useState(false)

  useEffect(() => {
    if (draftId) return
    toast.error("请先提出目标")
    navigate("#/")
  }, [draftId, navigate])

  useEffect(() => {
    if (!draftId) return
    let cancelled = false
    getTask(draftId)
      .then((data) => {
        if (cancelled) return
        setTask(data)
        const texts = data.constraints.map((constraint) => constraint.text)
        setConstraints(texts)
        setSeededConstraints(texts)
        setMode(data.advanced_mode)
        setRounds(data.advanced_rounds)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setLoadError(err instanceof Error ? err.message : "加载任务失败，请重试")
      })
    return () => {
      cancelled = true
    }
  }, [draftId])

  if (!draftId) return null

  const constraintsEdited = constraints.join("\n") !== seededConstraints.join("\n")

  const beginCollaboration = async () => {
    if (!task || starting) return
    let submitRounds = rounds
    if (mode === "debate" && submitRounds > 1) {
      submitRounds = 1
      toast.info("已按支持范围调整：辩论 1 轮")
    }
    setStarting(true)
    try {
      await startTask(task.id, {
        constraints,
        advanced_mode: mode,
        advanced_rounds: submitRounds,
      })
      navigate(`#/task/${task.id}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "启动失败，请重试")
    } finally {
      setStarting(false)
    }
  }

  return (
    <Shell
      title="新任务 · 确认协作计划"
      subtitle="第二步 · 确认后开始协作"
      topRight={
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-3 sm:flex">
            <span className="rounded-lg bg-success-bg px-[9px] py-[3px] text-xs font-medium text-success">
              ✓ 目标与材料
            </span>
            <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
            <span className="rounded-lg bg-accent px-[9px] py-[3px] text-xs font-medium text-primary">
              2 确认计划
            </span>
          </div>
          <ThemeToggle />
        </div>
      }
    >
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-7 px-6 py-10 lg:px-10">
        {loadError ? (
          <div
            role="alert"
            className="flex flex-col items-start gap-3 rounded-[10px] border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
          >
            <span>{loadError}</span>
            <button
              type="button"
              onClick={() => navigate("#/")}
              className={cn("rounded-md font-medium underline underline-offset-2", FOCUS_RING)}
            >
              返回首页
            </button>
          </div>
        ) : !task ? (
          <div className="flex h-full min-h-[420px] items-center justify-center">
            <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden />
            <span className="sr-only">正在加载协作计划</span>
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-3">
              <h1 className="text-[28px] font-bold text-foreground">让每个视角都有明确的任务</h1>
              <p className="text-base text-secondary-foreground">
                我们将围绕你的目标组织四个专业角色，在需要取舍时请你确认，而不是逐条等待你推进。
              </p>
            </div>
            <div className="flex flex-col items-stretch gap-6 xl:flex-row">
              <section className="flex w-full flex-col gap-5 rounded-[14px] border border-border bg-card p-6 xl:w-[392px] xl:shrink-0">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-lg font-bold text-foreground">目标与材料</h2>
                  <button
                    type="button"
                    onClick={() => toast("回到上一步即可修改目标与材料")}
                    className={cn(
                      "shrink-0 rounded-md text-[13px] text-primary hover:underline",
                      FOCUS_RING,
                    )}
                  >
                    调整 ✎
                  </button>
                </div>
                {constraintsEdited ? (
                  <span className="self-start rounded-lg bg-accent px-2 py-1 text-xs text-primary">
                    约束已修改 · 将同步到工作区
                  </span>
                ) : null}
                <div className="flex flex-col gap-2">
                  <span className="text-[13px] text-muted-foreground">要做出的判断</span>
                  <span className="break-words text-[22px] leading-snug font-bold text-foreground">
                    {task.goal_text}
                  </span>
                </div>
                <div className="flex flex-col gap-2">
                  <span className="text-[13px] text-muted-foreground">期望成果</span>
                  <span className="text-base font-medium break-words text-primary">
                    {task.expected_outcome || "尚未填写"}
                  </span>
                </div>
                <hr className="border-border" />
                <div className="flex flex-col gap-2">
                  <span className="text-[13px] text-muted-foreground">上下文约束</span>
                  <ConstraintEditor constraints={constraints} onChange={setConstraints} />
                </div>
                <hr className="border-border" />
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between gap-3 text-[13px]">
                    <span className="text-muted-foreground">
                      已添加材料 · {task.materials.length} 项
                    </span>
                    <button
                      type="button"
                      onClick={() => toast.info("回到上一步的「添加材料」入口")}
                      className={cn("rounded-md text-primary hover:underline", FOCUS_RING)}
                    >
                      ＋ 添加
                    </button>
                  </div>
                  {task.materials.map((material, index) => (
                    <div
                      key={`${material.name}-${index}`}
                      className="flex items-center gap-2 rounded-lg bg-panel p-2.5 text-[13px] text-secondary-foreground"
                    >
                      <FileText className="size-4 shrink-0" aria-hidden />
                      <span className="min-w-0 truncate">{material.name}</span>
                    </div>
                  ))}
                </div>
              </section>
              <section className="flex min-w-0 flex-1 flex-col gap-5 rounded-[14px] border border-border bg-card p-6">
                <RoleDuties
                  headerAction={
                    <button
                      type="button"
                      onClick={() => setExpertPanelOpen(true)}
                      className={cn(
                        "shrink-0 rounded-md text-[13px] text-secondary-foreground transition-colors hover:text-foreground",
                        FOCUS_RING,
                      )}
                    >
                      管理专家
                    </button>
                  }
                />
              </section>
            </div>
            <StagePath />
            <AdvancedSettings
              mode={mode}
              rounds={rounds}
              onMode={setMode}
              onRounds={setRounds}
            />
            <div className="flex flex-wrap items-center justify-between gap-4">
              <button
                type="button"
                onClick={() => navigate("#/")}
                className={cn(
                  "flex h-11 items-center gap-2 rounded-lg border border-border bg-card px-[18px] text-sm font-medium text-foreground transition-colors hover:bg-panel",
                  FOCUS_RING,
                )}
              >
                <ArrowLeft className="size-4" aria-hidden />
                返回上一步
              </button>
              <div className="flex flex-wrap items-center gap-4">
                <span className="text-[13px] text-muted-foreground">
                  讨论与成果草稿将同步展开
                </span>
                <button
                  type="button"
                  disabled={starting}
                  onClick={() => void beginCollaboration()}
                  className={cn(
                    "flex h-11 items-center gap-2 rounded-lg bg-primary px-[18px] text-sm font-bold text-primary-foreground transition-colors",
                    starting ? "cursor-not-allowed opacity-70" : "hover:bg-primary/90",
                    FOCUS_RING,
                  )}
                >
                  {starting ? (
                    <>
                      <Loader2 className="size-4 animate-spin" aria-hidden />
                      正在启动…
                    </>
                  ) : (
                    <>
                      开始协作
                      <ArrowRight className="size-4" aria-hidden />
                    </>
                  )}
                </button>
              </div>
            </div>
          </>
        )}
        <ExpertPanel
          open={expertPanelOpen}
          onClose={() => setExpertPanelOpen(false)}
        />
      </div>
    </Shell>
  )
}
