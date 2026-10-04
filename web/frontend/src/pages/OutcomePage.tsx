import { useCallback, useEffect, useState } from "react"
import {
  ArrowLeft,
  ArrowUpRight,
  CircleHelp,
  ClipboardCheck,
  Copy,
  Download,
  Loader2,
  MessagesSquare,
  Pencil,
  Save,
} from "lucide-react"
import { toast } from "sonner"
import { OutcomeOverview, pad } from "@/components/v2/OutcomeOverview"
import { Shell } from "@/components/v2/Shell"
import { ThemeToggle } from "@/components/v2/ThemeToggle"
import { useHashRoute } from "@/lib/router"
import { roleLabel, STAGE_LABELS } from "@/lib/roles"
import {
  confirmOutcome,
  exportUrl,
  getOutcome,
  getTask,
  patchOutcome,
  type OutcomePatchT,
  type OutcomeT,
  type StageT,
  type V2TaskT,
} from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING = "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
const TOP_BUTTON = cn(
  "flex h-9 items-center gap-1.5 rounded-lg border border-border bg-card px-3 text-[13px] font-medium text-foreground transition-colors hover:bg-panel disabled:pointer-events-none disabled:opacity-50",
  FOCUS_RING,
)
const PRIMARY_BUTTON = cn(
  "flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3 text-[13px] font-bold text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50",
  FOCUS_RING,
)
const EDIT_FIELD = "w-full rounded-lg border border-border bg-panel px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"

function splitLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
}

function stageLabel(stage?: StageT): string {
  return stage ? (STAGE_LABELS[stage] ?? stage) : ""
}

interface PathDraftT {
  name: string
  desc: string
  pros: string
  cons: string
  fit: string
  recommended: boolean
}

interface OutcomeDraftT {
  conclusion: string
  reasons: { title: string; body: string; refs: number[] }[]
  paths: PathDraftT[]
  actions: { title: string; detail: string; assignee: string; due: string }[]
}

function toDraft(outcome: OutcomeT): OutcomeDraftT {
  return {
    conclusion: outcome.conclusion ?? "",
    reasons: (outcome.reasons ?? []).map((reason) => ({
      title: reason.title ?? "",
      body: reason.body ?? "",
      refs: reason.refs ?? [],
    })),
    paths: (outcome.path_comparison ?? []).map((path) => ({
      name: path.name ?? "",
      desc: path.desc ?? "",
      pros: (path.pros ?? []).join("\n"),
      cons: (path.cons ?? []).join("\n"),
      fit: path.fit ?? "",
      recommended: path.recommended ?? false,
    })),
    actions: (outcome.actions ?? []).map((action) => ({
      title: action.title ?? "",
      detail: action.detail ?? "",
      assignee: action.assignee || "待分配",
      due: action.due || "待确定",
    })),
  }
}

function buildMarkdown(outcome: OutcomeT): string {
  const lines: string[] = []
  lines.push(`# 决策成果：${outcome.conclusion ?? ""}`.trimEnd())

  const reasons = outcome.reasons ?? []
  if (reasons.length > 0) {
    lines.push("", "## 为什么")
    for (const reason of reasons) {
      if (reason.title) lines.push(`### ${reason.title}`)
      if (reason.body) lines.push(reason.body)
      if (reason.refs?.length) {
        lines.push(`关联讨论 ${reason.refs.map((ref) => `#${pad(ref)}`).join(" · ")}`)
      }
    }
  }

  const paths = outcome.path_comparison ?? []
  if (paths.length > 0) {
    lines.push("", "## 路径对比")
    for (const path of paths) {
      lines.push(`### ${path.name ?? ""}${path.recommended ? "（建议路径）" : ""}`.trimEnd())
      if (path.desc) lines.push(path.desc)
      if (path.pros?.length) lines.push(`优势：${path.pros.join("；")}`)
      if (path.cons?.length) lines.push(`代价/限制：${path.cons.join("；")}`)
      if (path.fit) lines.push(`前提：${path.fit}`)
    }
  }

  const evidence = outcome.evidence ?? []
  if (evidence.length > 0) {
    lines.push("", "## 依据（本次讨论记录，非外部文献）")
    for (const item of evidence) {
      lines.push(
        `- #${pad(item.seq_ref ?? 0)} · ${stageLabel(item.stage)} · ${item.author ?? ""}：${item.quote ?? ""}`,
      )
    }
  }

  const actions = outcome.actions ?? []
  if (actions.length > 0) {
    lines.push("", "## 把建议变成下一步")
    actions.forEach((action, index) => {
      const meta = [action.assignee, action.due].filter(Boolean).join(" · ")
      const detail = action.detail ? ` — ${action.detail}` : ""
      lines.push(`${index + 1}. ${action.title ?? ""}${detail}${meta ? `（${meta}）` : ""}`)
    })
  }

  const acceptance = outcome.acceptance ?? []
  if (acceptance.length > 0) {
    lines.push("", "## 通过这些条件再扩展")
    for (const item of acceptance) {
      lines.push(`- ${item.title ?? ""}${item.detail ? `：${item.detail}` : ""}`)
    }
  }

  const questions = outcome.open_questions ?? []
  if (questions.length > 0) {
    lines.push("", "## 仍需解决的问题")
    for (const question of questions) lines.push(`- ${question}`)
  }

  lines.push("", "> 以上为 AI 协作建议，非团队决议。")
  return lines.join("\n")
}

function SectionHeader({ index, title }: { index: string; title: string }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="font-mono text-[13px] text-primary">{index}</span>
      <h2 className="text-xl font-bold text-foreground">{title}</h2>
    </div>
  )
}

export function OutcomePage({ id }: { id: string }) {
  const { navigate } = useHashRoute()
  const [task, setTask] = useState<V2TaskT | null>(null)
  const [outcome, setOutcome] = useState<OutcomeT | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<OutcomeDraftT | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirming, setConfirming] = useState(false)

  useEffect(() => {
    let cancelled = false
    setTask(null)
    setOutcome(null)
    setLoadError(null)
    setEditing(false)
    setDraft(null)
    const load = async () => {
      try {
        const data = await getTask(id)
        if (cancelled) return
        if (data.status !== "completed") {
          toast.info("协作完成后可查看成果")
          navigate(`#/task/${id}`)
          return
        }
        setTask(data)
        const doc = await getOutcome(id)
        if (cancelled) return
        setOutcome(doc)
      } catch (err) {
        if (cancelled) return
        setLoadError(err instanceof Error ? err.message : "加载成果失败")
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [id, navigate])

  const handleConfirm = useCallback(async () => {
    if (confirming) return
    setConfirming(true)
    try {
      const doc = await confirmOutcome(id)
      setOutcome(doc)
      toast.success("已标记为团队已确认")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "操作失败，请稍后再试")
    } finally {
      setConfirming(false)
    }
  }, [id, confirming])

  const focusTurn = useCallback(
    (seq: number) => {
      sessionStorage.setItem("v2FocusTurn", String(seq))
      navigate(`#/task/${id}`)
    },
    [id, navigate],
  )

  const startEdit = () => {
    if (!outcome) return
    setDraft(toDraft(outcome))
    setEditing(true)
  }

  const handleCancel = () => {
    setDraft(null)
    setEditing(false)
  }

  const handleSave = async () => {
    if (!outcome || !draft || saving) return
    setSaving(true)
    try {
      const patch: OutcomePatchT = {
        conclusion: draft.conclusion,
        summary_groups: {
          confirmed: outcome.summary_groups?.confirmed ?? [],
          disputed: outcome.summary_groups?.disputed ?? [],
          unverified: outcome.summary_groups?.unverified ?? [],
        },
        reasons: draft.reasons,
        path_comparison: draft.paths.map((path) => ({
          name: path.name,
          desc: path.desc,
          pros: splitLines(path.pros),
          cons: splitLines(path.cons),
          fit: path.fit,
          recommended: path.recommended,
        })),
        evidence: outcome.evidence ?? [],
        open_questions: outcome.open_questions ?? [],
        actions: draft.actions,
        acceptance: outcome.acceptance ?? [],
      }
      await patchOutcome(id, patch)
      const fresh = await getOutcome(id)
      setOutcome(fresh)
      setEditing(false)
      setDraft(null)
      toast.success("已保存")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败，请稍后再试")
    } finally {
      setSaving(false)
    }
  }

  const handleCopy = async () => {
    if (!outcome) return
    try {
      await navigator.clipboard.writeText(buildMarkdown(outcome))
      toast.success("已复制 Markdown")
    } catch {
      toast.error("复制失败，请检查浏览器剪贴板权限")
    }
  }

  const continueDiscussion = () => {
    const question = outcome?.open_questions?.[0]
    if (question) sessionStorage.setItem("v2FollowUp", question)
    navigate(`#/task/${id}`)
  }

  if (loadError) {
    return (
      <Shell title="决策成果" topRight={<ThemeToggle />}>
        <div className="flex flex-col items-center justify-center gap-4 p-16">
          <p className="text-sm text-muted-foreground">{loadError}</p>
          <button
            type="button"
            onClick={() => navigate("#/")}
            className={cn(
              "flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-[13px] text-foreground transition-colors hover:bg-panel",
              FOCUS_RING,
            )}
          >
            <ArrowLeft className="size-4" aria-hidden />
            返回首页
          </button>
        </div>
      </Shell>
    )
  }

  if (!task || !outcome) {
    return (
      <Shell title="载入中…" topRight={<ThemeToggle />}>
        <div className="flex items-center justify-center p-16" role="status" aria-label="载入中">
          <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden />
        </div>
      </Shell>
    )
  }

  const label = outcome.label ?? "ai_suggestion"
  const reasons = outcome.reasons ?? []
  const paths = outcome.path_comparison ?? []
  const evidence = outcome.evidence ?? []
  const actions = outcome.actions ?? []
  const questions = outcome.open_questions ?? []
  const acceptance = outcome.acceptance ?? []

  const confirmedConstraint =
    task.constraints.find((constraint) => constraint.confirmed)?.text ??
    outcome.summary_groups?.confirmed?.[0] ??
    null
  let confirmedSeq: number | null = null
  if (confirmedConstraint) {
    const matched = task.turns.find(
      (turn) =>
        turn.kind === "decision_record" &&
        (turn.title.includes(confirmedConstraint) || turn.body.includes(confirmedConstraint)),
    )
    const record = matched ?? task.turns.find((turn) => turn.kind === "decision_record")
    if (record && record.seq > 0) confirmedSeq = record.seq
  }

  const updateReason = (index: number, part: Partial<{ title: string; body: string }>) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            reasons: prev.reasons.map((item, i) => (i === index ? { ...item, ...part } : item)),
          }
        : prev,
    )
  }

  const updatePath = (index: number, part: Partial<PathDraftT>) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            paths: prev.paths.map((item, i) => (i === index ? { ...item, ...part } : item)),
          }
        : prev,
    )
  }

  const updateAction = (index: number, part: Partial<{ title: string; detail: string }>) => {
    setDraft((prev) =>
      prev
        ? {
            ...prev,
            actions: prev.actions.map((item, i) => (i === index ? { ...item, ...part } : item)),
          }
        : prev,
    )
  }

  return (
    <Shell
      title="决策成果"
      subtitle={`${task.goal_text} · 已完成协作 · 第 4 / 4 阶段`}
      topRight={
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <button
                type="button"
                disabled={saving}
                onClick={() => void handleSave()}
                className={PRIMARY_BUTTON}
              >
                {saving ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <Save className="size-4" aria-hidden />
                )}
                保存
              </button>
              <button type="button" onClick={handleCancel} className={TOP_BUTTON}>
                取消
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={startEdit} className={TOP_BUTTON}>
                <Pencil className="size-4" aria-hidden />
                编辑成果
              </button>
              <button
                type="button"
                onClick={() => void handleCopy()}
                className={TOP_BUTTON}
              >
                <Copy className="size-4" aria-hidden />
                复制
              </button>
              <button
                type="button"
                onClick={() => window.open(exportUrl(id))}
                className={TOP_BUTTON}
              >
                <Download className="size-4" aria-hidden />
                导出
              </button>
            </>
          )}
          <ThemeToggle />
        </div>
      }
    >
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-7 p-10">
        <OutcomeOverview
          outcome={outcome}
          confirmedText={confirmedConstraint}
          confirmedSeq={confirmedSeq}
          confirming={confirming}
          onConfirm={() => void handleConfirm()}
        />

        <div className="flex flex-col items-start gap-7 xl:flex-row">
          <section
            aria-label="成果正文"
            className="flex w-full min-w-0 flex-col gap-7 rounded-[14px] border border-border bg-card p-7 xl:flex-1"
          >
            <div className="flex flex-col gap-5">
              <SectionHeader index="01" title="为什么是内部试点" />
              {reasons.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无建议理由</p>
              ) : (
                <div className="flex flex-col gap-5">
                  {reasons.map((reason, index) => (
                    <div key={index} className="flex flex-col gap-1.5">
                      {editing && draft ? (
                        <input
                          value={draft.reasons[index]?.title ?? ""}
                          onChange={(event) => updateReason(index, { title: event.target.value })}
                          aria-label={`理由 ${index + 1} 标题`}
                          className={EDIT_FIELD}
                        />
                      ) : (
                        reason.title ? (
                          <h3 className="text-base font-bold text-foreground">{reason.title}</h3>
                        ) : null
                      )}
                      {editing && draft ? (
                        <textarea
                          value={draft.reasons[index]?.body ?? ""}
                          onChange={(event) => updateReason(index, { body: event.target.value })}
                          aria-label={`理由 ${index + 1} 正文`}
                          rows={3}
                          className={cn(EDIT_FIELD, "resize-y leading-relaxed")}
                        />
                      ) : (
                        reason.body ? (
                          <p className="text-[15px] text-secondary-foreground">{reason.body}</p>
                        ) : null
                      )}
                      {(reason.refs ?? []).length > 0 ? (
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                          {(reason.refs ?? []).map((ref) => (
                            <button
                              key={ref}
                              type="button"
                              onClick={() => focusTurn(ref)}
                              className={cn(
                                "text-xs text-success underline underline-offset-2 transition-colors hover:text-success/80",
                                FOCUS_RING,
                              )}
                            >
                              关联讨论 #{pad(ref)} ↗
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <hr className="border-border" />

            <div className="flex flex-col gap-5">
              <SectionHeader index="02" title="两条可行路径，分别承担什么" />
              {paths.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无路径对比</p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {paths.map((path, index) => (
                    <article
                      key={index}
                      className={cn(
                        "flex flex-col gap-3.5 rounded-[10px] p-[18px]",
                        path.recommended ? "border border-accent-border bg-accent" : "bg-panel",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        {editing && draft ? (
                          <input
                            value={draft.paths[index]?.name ?? ""}
                            onChange={(event) => updatePath(index, { name: event.target.value })}
                            aria-label={`路径 ${index + 1} 名称`}
                            className={EDIT_FIELD}
                          />
                        ) : (
                          <h3 className="text-[17px] font-bold text-foreground">{path.name}</h3>
                        )}
                        {path.recommended ? (
                          <span className="shrink-0 rounded-lg bg-card px-2 py-0.5 text-xs font-medium text-primary">
                            建议路径
                          </span>
                        ) : null}
                      </div>
                      {editing && draft ? (
                        <textarea
                          value={draft.paths[index]?.desc ?? ""}
                          onChange={(event) => updatePath(index, { desc: event.target.value })}
                          aria-label={`路径 ${index + 1} 说明`}
                          rows={2}
                          className={cn(EDIT_FIELD, "resize-y")}
                        />
                      ) : (
                        path.desc ? (
                          <p className="text-sm text-secondary-foreground">{path.desc}</p>
                        ) : null
                      )}
                      <hr className="border-border" />
                      {editing && draft ? (
                        <>
                          <textarea
                            value={draft.paths[index]?.pros ?? ""}
                            onChange={(event) => updatePath(index, { pros: event.target.value })}
                            aria-label={`路径 ${index + 1} 优势（每行一条）`}
                            rows={2}
                            className={cn(EDIT_FIELD, "resize-y")}
                          />
                          <textarea
                            value={draft.paths[index]?.cons ?? ""}
                            onChange={(event) => updatePath(index, { cons: event.target.value })}
                            aria-label={`路径 ${index + 1} 代价/限制（每行一条）`}
                            rows={2}
                            className={cn(EDIT_FIELD, "resize-y")}
                          />
                          <input
                            value={draft.paths[index]?.fit ?? ""}
                            onChange={(event) => updatePath(index, { fit: event.target.value })}
                            aria-label={`路径 ${index + 1} 前提`}
                            className={EDIT_FIELD}
                          />
                        </>
                      ) : (
                        <>
                          {(path.pros ?? []).length > 0 ? (
                            <p className="text-sm text-foreground">
                              优势：{(path.pros ?? []).join("；")}
                            </p>
                          ) : null}
                          {(path.cons ?? []).length > 0 ? (
                            <p className="text-sm text-secondary-foreground">
                              代价/限制：{(path.cons ?? []).join("；")}
                            </p>
                          ) : null}
                          {path.fit ? (
                            <p
                              className={cn(
                                "text-[13px]",
                                path.recommended ? "text-primary" : "text-muted-foreground",
                              )}
                            >
                              前提：{path.fit}
                            </p>
                          ) : null}
                        </>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>

            <hr className="border-border" />

            <div className="flex flex-col gap-4">
              <SectionHeader index="03" title="回到讨论，看见建议的来路" />
              <p className="text-[13px] text-muted-foreground">
                以下为本次讨论记录，不是外部文献或已验证事实。
              </p>
              {evidence.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无依据记录</p>
              ) : (
                <div>
                  {evidence.map((item, index) => {
                    const seqRef = item.seq_ref ?? 0
                    const jumpable = seqRef > 0
                    const row = (
                      <>
                        <span className="flex w-[166px] shrink-0 flex-col">
                          <span className="text-[13px] font-medium text-success">
                            #{pad(seqRef)} · {stageLabel(item.stage)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {roleLabel(item.author ?? "")}
                          </span>
                        </span>
                        <span className="flex-1 text-sm text-secondary-foreground">
                          {item.quote}
                        </span>
                        <ArrowUpRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                      </>
                    )
                    return jumpable ? (
                      <button
                        key={index}
                        type="button"
                        onClick={() => focusTurn(seqRef)}
                        className={cn(
                          "flex w-full items-start gap-4 border-b border-border py-2.5 text-left transition-colors last:border-b-0 hover:bg-panel/60",
                          FOCUS_RING,
                        )}
                      >
                        {row}
                      </button>
                    ) : (
                      <div
                        key={index}
                        className="flex w-full items-start gap-4 border-b border-border py-2.5 last:border-b-0"
                      >
                        {row}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            <hr className="border-border" />

            <div className="flex flex-col gap-5">
              <SectionHeader index="04" title="把建议变成下一步" />
              {actions.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无行动项</p>
              ) : (
                <div className="flex flex-col gap-4">
                  {actions.map((action, index) => (
                    <div key={index} className="flex gap-3.5">
                      <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent font-mono text-xs text-primary">
                        {index + 1}
                      </span>
                      <div className="flex min-w-0 flex-col gap-1">
                        {editing && draft ? (
                          <input
                            value={draft.actions[index]?.title ?? ""}
                            onChange={(event) => updateAction(index, { title: event.target.value })}
                            aria-label={`行动项 ${index + 1} 标题`}
                            className={EDIT_FIELD}
                          />
                        ) : (
                          <h3 className="text-[15px] font-bold text-foreground">{action.title}</h3>
                        )}
                        {editing && draft ? (
                          <textarea
                            value={draft.actions[index]?.detail ?? ""}
                            onChange={(event) => updateAction(index, { detail: event.target.value })}
                            aria-label={`行动项 ${index + 1} 说明`}
                            rows={2}
                            className={cn(EDIT_FIELD, "resize-y")}
                          />
                        ) : (
                          action.detail ? (
                            <p className="text-sm text-secondary-foreground">{action.detail}</p>
                          ) : null
                        )}
                        {editing ? null : (
                          <p className="text-xs text-muted-foreground">
                            {action.assignee || "待分配"} · {action.due || "待确定"}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <aside className="flex w-full shrink-0 flex-col gap-6 xl:w-[320px]">
            <section
              aria-label="仍需解决的问题"
              className="flex flex-col gap-[18px] rounded-[14px] border border-warning-border bg-warning-bg p-6"
            >
              <div className="flex items-center gap-3">
                <CircleHelp className="size-20 shrink-0 text-warning" aria-hidden />
                <h2 className="text-lg font-bold text-foreground">仍需解决的问题</h2>
              </div>
              {questions.length > 0 ? (
                <ul className="flex flex-col gap-2.5">
                  {questions.map((question, index) => (
                    <li key={index} className="flex items-start gap-2.5">
                      <span
                        className="mt-[9px] size-[5px] shrink-0 rounded-full bg-warning"
                        aria-hidden
                      />
                      <span className="text-[15px] text-secondary-foreground">{question}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">暂无待解决问题</p>
              )}
              <p className="text-[13px] text-warning">
                这些问题尚未验证；不影响先提交试点建议，但会影响是否扩大采用。
              </p>
              <button
                type="button"
                onClick={continueDiscussion}
                className={cn(
                  "flex h-11 w-full items-center justify-center gap-2 rounded-lg border border-border bg-card text-sm font-medium text-foreground transition-colors hover:bg-panel",
                  FOCUS_RING,
                )}
              >
                <MessagesSquare className="size-4" aria-hidden />
                继续讨论
              </button>
            </section>

            <section
              aria-label="通过这些条件再扩展"
              className="flex flex-col gap-4 rounded-[14px] border border-border bg-card p-6"
            >
              <div className="flex items-center gap-3">
                <ClipboardCheck className="size-20 shrink-0 text-primary" aria-hidden />
                <h2 className="text-lg font-bold text-foreground">通过这些条件再扩展</h2>
              </div>
              <span className="self-start rounded-lg bg-success-bg px-2 py-0.5 text-xs font-medium text-success">
                已确认边界
              </span>
              {acceptance.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无验收条件</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {acceptance.map((item, index) => (
                    <div key={index} className="flex flex-col gap-0.5">
                      {item.title ? (
                        <span className="text-sm font-bold text-foreground">{item.title}</span>
                      ) : null}
                      {item.detail ? (
                        <span className="text-sm text-secondary-foreground">{item.detail}</span>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section
              aria-label="审批说明"
              className="flex flex-col gap-1.5 rounded-[14px] border border-border bg-card p-4"
            >
              <h2 className="text-sm font-bold text-foreground">审批说明</h2>
              <p className="text-[13px] text-muted-foreground">
                本页为 AI 协作建议，需团队审批后执行；「标记为团队已确认」仅记录你的选择，不产生真实审批流。
              </p>
            </section>
          </aside>
        </div>

        <footer className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={() => navigate(`#/task/${id}`)}
            className={cn(
              "flex items-center gap-1.5 self-start text-[13px] text-primary transition-colors hover:text-primary/80",
              FOCUS_RING,
            )}
          >
            <ArrowLeft className="size-4" aria-hidden />
            返回讨论
          </button>
          <span className="text-[13px] text-muted-foreground">
            {label === "team_confirmed" ? "成果已由你标记为团队已确认" : "以上为 AI 协作建议，非团队决议"}
          </span>
        </footer>
      </div>
    </Shell>
  )
}
