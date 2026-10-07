import { useCallback, useEffect, useState } from "react"
import { Ban, Loader2, Trash2, X } from "lucide-react"
import { toast } from "sonner"
import {
  addExpert,
  deleteExpert,
  listExperts,
  updateExpert,
  type ExpertT,
} from "@/lib/v2api"
import { cn } from "@/lib/utils"

const FOCUS_RING =
  "focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"

const PRESET_TAGS = ["研究", "设计", "挑战", "权衡", "数据", "评审"]

const INPUT_CLASS =
  "h-9 w-full rounded-lg border border-border bg-card px-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"

function ProbeBadge({ state }: { state: ExpertT["probe"] }) {
  if (state === "up") {
    return (
      <span className="inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-success">
        <span className="size-1.5 rounded-full bg-success" aria-hidden />
        在线
      </span>
    )
  }
  if (state === "down") {
    return (
      <span className="inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-destructive">
        <span className="size-1.5 rounded-full bg-destructive" aria-hidden />
        离线
      </span>
    )
  }
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5 text-xs font-medium text-muted-foreground">
      <span className="size-1.5 rounded-full bg-muted-foreground" aria-hidden />
      未知
    </span>
  )
}

function ExpertRow({
  expert,
  onToggle,
  onDelete,
}: {
  expert: ExpertT
  onToggle: (expert: ExpertT) => void
  onDelete: (expert: ExpertT) => void
}) {
  return (
    <li className="flex items-center gap-3 rounded-[10px] border border-border p-3">
      <span className="text-xl" aria-hidden>
        {expert.emoji}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium text-foreground">{expert.name}</span>
          {expert.source === "builtin" ? (
            <span className="shrink-0 rounded bg-panel px-1.5 py-px text-[11px] text-muted-foreground">
              内置
            </span>
          ) : null}
        </span>
        {expert.card_name ? (
          <span className="truncate text-xs text-muted-foreground">{expert.card_name}</span>
        ) : null}
        <span className="truncate text-xs text-muted-foreground">{expert.url}</span>
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
        {expert.tags.map((tag) => (
          <span key={tag} className="rounded bg-panel px-1.5 py-0.5 text-[11px] text-secondary-foreground">
            {tag}
          </span>
        ))}
      </div>
      <ProbeBadge state={expert.probe} />
      <button
        type="button"
        role="switch"
        aria-checked={expert.enabled}
        aria-label={expert.enabled ? `禁用 ${expert.name}` : `启用 ${expert.name}`}
        title={expert.enabled ? "禁用" : "启用"}
        onClick={() => onToggle(expert)}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
          expert.enabled ? "bg-success" : "bg-input",
          FOCUS_RING,
        )}
      >
        <span
          aria-hidden
          className={cn(
            "absolute top-0.5 size-4 rounded-full bg-white transition-all",
            expert.enabled ? "left-[18px]" : "left-0.5",
          )}
        />
      </button>
      {expert.source === "custom" ? (
        <button
          type="button"
          aria-label={`删除 ${expert.name}`}
          title="删除"
          onClick={() => onDelete(expert)}
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive",
            FOCUS_RING,
          )}
        >
          <Trash2 className="size-4" aria-hidden />
        </button>
      ) : (
        <button
          type="button"
          aria-label={`禁用 ${expert.name}`}
          title="禁用"
          onClick={() => onToggle(expert)}
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-panel hover:text-foreground",
            FOCUS_RING,
          )}
        >
          <Ban className="size-4" aria-hidden />
        </button>
      )}
    </li>
  )
}

export function ExpertPanel({
  open,
  onClose,
  onChanged,
}: {
  open: boolean
  onClose: () => void
  onChanged?: () => void
}) {
  const [experts, setExperts] = useState<ExpertT[]>([])
  const [loading, setLoading] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [name, setName] = useState("")
  const [url, setUrl] = useState("")
  const [tags, setTags] = useState<string[]>([])
  const [freeTag, setFreeTag] = useState("")
  const [emoji, setEmoji] = useState("🔌")
  const [submitting, setSubmitting] = useState(false)

  const refresh = useCallback(() => {
    setLoading(true)
    listExperts()
      .then((data) => setExperts(data))
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : "加载专家失败，请重试")
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!open) return
    refresh()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [open, refresh, onClose])

  if (!open) return null

  const toggleExpert = (expert: ExpertT) => {
    updateExpert(expert.id, { enabled: !expert.enabled })
      .then(() => {
        toast.success(expert.enabled ? "已禁用" : "已启用")
        refresh()
        onChanged?.()
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : "操作失败，请重试")
      })
  }

  const removeExpert = (expert: ExpertT) => {
    if (!window.confirm("删除该专家？")) return
    deleteExpert(expert.id)
      .then(() => {
        toast.success("已删除")
        refresh()
        onChanged?.()
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : "删除失败，请重试")
      })
  }

  const toggleTag = (tag: string) => {
    setTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
    )
  }

  const addFreeTag = () => {
    const tag = freeTag.trim()
    if (!tag || tags.includes(tag)) {
      setFreeTag("")
      return
    }
    setTags((prev) => [...prev, tag])
    setFreeTag("")
  }

  const submit = () => {
    const trimmedName = name.trim()
    const trimmedUrl = url.trim()
    if (!trimmedName || !trimmedUrl || submitting) return
    setSubmitting(true)
    addExpert({
      name: trimmedName,
      url: trimmedUrl,
      tags,
      emoji: emoji.trim() || undefined,
    })
      .then(() => {
        toast.success("专家已注册")
        setName("")
        setUrl("")
        setTags([])
        setFreeTag("")
        setEmoji("🔌")
        setFormOpen(false)
        refresh()
        onChanged?.()
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : "注册失败，请重试")
      })
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="专家库">
      <button
        type="button"
        aria-label="关闭专家库"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-black/40"
      />
      <div className="relative mx-auto mt-[8vh] flex max-h-[84vh] w-full max-w-[560px] flex-col overflow-y-auto rounded-[14px] border border-border bg-card p-6">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-foreground">专家库</h2>
          <button
            type="button"
            aria-label="关闭专家库"
            onClick={onClose}
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-panel hover:text-foreground",
              FOCUS_RING,
            )}
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        {loading && experts.length === 0 ? (
          <div className="flex min-h-[160px] items-center justify-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden />
            <span className="sr-only">正在加载专家列表</span>
          </div>
        ) : (
          <ul className="mt-4 flex flex-col gap-2">
            {experts.map((expert) => (
              <ExpertRow
                key={expert.id}
                expert={expert}
                onToggle={toggleExpert}
                onDelete={removeExpert}
              />
            ))}
            {!loading && experts.length === 0 ? (
              <li className="rounded-[10px] border border-border p-3 text-xs text-muted-foreground">
                暂无专家，可从下方注册
              </li>
            ) : null}
          </ul>
        )}
        <div className="mt-4 flex flex-col gap-3">
          <button
            type="button"
            aria-expanded={formOpen}
            onClick={() => setFormOpen((prev) => !prev)}
            className={cn(
              "self-start rounded-md text-[13px] font-medium text-primary hover:underline",
              FOCUS_RING,
            )}
          >
            ＋ 添加专家
          </button>
          {formOpen ? (
            <form
              onSubmit={(event) => {
                event.preventDefault()
                submit()
              }}
              className="flex flex-col gap-3 rounded-[10px] border border-border bg-panel p-3"
            >
              <div className="flex flex-col gap-1.5">
                <label htmlFor="expert-name" className="text-xs text-muted-foreground">
                  名称
                </label>
                <input
                  id="expert-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="如：设计师 · Hermes"
                  className={INPUT_CLASS}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="expert-url" className="text-xs text-muted-foreground">
                  地址
                </label>
                <input
                  id="expert-url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="http(s)://…"
                  className={INPUT_CLASS}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-muted-foreground">标签</span>
                <div className="flex flex-wrap gap-1.5">
                  {PRESET_TAGS.map((tag) => {
                    const active = tags.includes(tag)
                    return (
                      <button
                        key={tag}
                        type="button"
                        aria-pressed={active}
                        onClick={() => toggleTag(tag)}
                        className={cn(
                          "rounded-lg border px-2 py-1 text-[11px] transition-colors",
                          active
                            ? "border-accent-border bg-accent text-primary"
                            : "border-border bg-card text-secondary-foreground hover:bg-panel",
                          FOCUS_RING,
                        )}
                      >
                        {tag}
                      </button>
                    )
                  })}
                  {tags
                    .filter((tag) => !PRESET_TAGS.includes(tag))
                    .map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        aria-pressed
                        onClick={() => toggleTag(tag)}
                        className={cn(
                          "rounded-lg border border-accent-border bg-accent px-2 py-1 text-[11px] text-primary transition-colors",
                          FOCUS_RING,
                        )}
                      >
                        {tag} ✕
                      </button>
                    ))}
                </div>
                <input
                  value={freeTag}
                  onChange={(event) => setFreeTag(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault()
                      addFreeTag()
                    }
                  }}
                  placeholder="自定义标签，回车添加"
                  aria-label="自定义标签"
                  className={INPUT_CLASS}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="expert-emoji" className="text-xs text-muted-foreground">
                  图标（可选）
                </label>
                <input
                  id="expert-emoji"
                  value={emoji}
                  maxLength={4}
                  onChange={(event) => setEmoji(event.target.value)}
                  className={cn(INPUT_CLASS, "w-20")}
                />
              </div>
              <button
                type="submit"
                disabled={submitting || !name.trim() || !url.trim()}
                className={cn(
                  "flex h-9 items-center justify-center gap-2 rounded-lg bg-primary text-sm font-bold text-primary-foreground transition-colors",
                  submitting || !name.trim() || !url.trim()
                    ? "cursor-not-allowed opacity-70"
                    : "hover:bg-primary/90",
                  FOCUS_RING,
                )}
              >
                {submitting ? (
                  <>
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                    正在注册…
                  </>
                ) : (
                  "注册专家"
                )}
              </button>
            </form>
          ) : null}
        </div>
      </div>
    </div>
  )
}
