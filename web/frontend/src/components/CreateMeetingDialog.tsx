import { useEffect, useState } from "react"
import { GitBranch, Loader2, MessagesSquare, Swords } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { Meeting, MeetingMode, Persona } from "@/types"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"

const MODE_OPTIONS: ReadonlyArray<{
  value: MeetingMode
  title: string
  desc: string
  chain: string
  icon: typeof GitBranch
}> = [
  {
    value: "pipeline",
    title: "流水线",
    desc: "按提交交付与质量门禁",
    chain: "Research → Writing → Review → Code → Summary",
    icon: GitBranch,
  },
  {
    value: "roundtable",
    title: "圆桌",
    desc: "Moderator 主持 · 1–10 轮",
    chain: "Moderator + Ada + Linus + Turing + Sage",
    icon: MessagesSquare,
  },
  {
    value: "debate",
    title: "辩论",
    desc: "正反交锋 + 裁判总结",
    chain: "正方人格 ⚡ 反方人格 ⚡ Judge",
    icon: Swords,
  },
]

export function CreateMeetingDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (meeting: Meeting) => void
}) {
  const [topic, setTopic] = useState("")
  const [mode, setMode] = useState<MeetingMode>("pipeline")
  const [maxRounds, setMaxRounds] = useState(1)
  const [autoPlay, setAutoPlay] = useState(false)
  const [inquiry, setInquiry] = useState(true)
  const [proPersona, setProPersona] = useState("socrates")
  const [conPersona, setConPersona] = useState("hume")
  const [personas, setPersonas] = useState<Persona[]>([])
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    api
      .listPersonas()
      .then(setPersonas)
      .catch(() => toast.error("加载人格列表失败"))
  }, [open])

  const roundsCap = mode === "debate" ? 3 : 10

  const submit = async () => {
    if (!topic.trim() || submitting) return
    setSubmitting(true)
    try {
      const meeting = await api.createMeeting({
        topic: topic.trim(),
        mode,
        max_rounds: mode === "pipeline" ? 1 : maxRounds,
        auto_play: autoPlay,
        pro_persona: proPersona,
        con_persona: conPersona,
        inquiry_enabled: inquiry,
      })
      setTopic("")
      setMaxRounds(1)
      setAutoPlay(false)
      setInquiry(true)
      onCreated(meeting)
    } catch {
      toast.error("创建会议失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            新建会议
            <span className="rounded-full border px-2 py-px font-mono text-[9px] uppercase tracking-[0.08em] text-assist">
              CONFIG
            </span>
          </DialogTitle>
          <DialogDescription>定义主题、讨论模式与参与规则</DialogDescription>
        </DialogHeader>

        <div className="grid gap-6 sm:grid-cols-2">
          {/* 左栏：主题 + 模式 */}
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="topic">会议主题</Label>
              <Input
                id="topic"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="输入会议主题，例如：A2A protocol"
              />
            </div>
            <div className="space-y-2">
              <Label>选择会议模式</Label>
              <RadioGroup
                value={mode}
                onValueChange={(v) => setMode(v as MeetingMode)}
                className="gap-2"
              >
                {MODE_OPTIONS.map((opt) => (
                  <Label
                    key={opt.value}
                    className={cn(
                      "flex cursor-pointer items-start gap-3 rounded-[14px] border p-3",
                      "has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-primary/5",
                    )}
                  >
                    <RadioGroupItem value={opt.value} className="mt-0.5" />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <opt.icon className="h-4 w-4 text-primary" />
                        <span className="font-bold">{opt.title}</span>
                      </span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">{opt.desc}</span>
                      <span className="mt-1 block truncate font-mono text-[9px] uppercase tracking-[0.06em] text-muted-foreground/70">
                        {opt.chain}
                      </span>
                    </span>
                  </Label>
                ))}
              </RadioGroup>
            </div>
          </div>

          {/* 右栏：参数 */}
          <div className="space-y-4 rounded-[14px] border p-4">
            {mode === "debate" && (
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold">辩论参数</span>
                <span className="rounded-full border px-2 py-px font-mono text-[9px] uppercase tracking-[0.08em] text-assist">
                  已选择
                </span>
              </div>
            )}
            {(mode === "roundtable" || mode === "debate") && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>{mode === "debate" ? "辩论轮数" : "讨论轮数"}</Label>
                  <span className="font-mono text-xs text-assist">{maxRounds} 轮</span>
                </div>
                <Slider
                  min={1}
                  max={roundsCap}
                  step={1}
                  value={[maxRounds]}
                  onValueChange={([v]) => setMaxRounds(v)}
                />
              </div>
            )}
            {mode === "debate" && (
              <>
                <div className="space-y-2">
                  <Label>正方人格</Label>
                  <Select value={proPersona} onValueChange={setProPersona}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {personas.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.avatar} {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>反方人格</Label>
                  <Select value={conPersona} onValueChange={setConPersona}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {personas.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.avatar} {p.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="inquiry">允许观众质询</Label>
                    <div className="text-xs text-muted-foreground">用户插话将附带给双方 Agent</div>
                  </div>
                  <Switch id="inquiry" checked={inquiry} onCheckedChange={setInquiry} />
                </div>
              </>
            )}
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="autoplay">自动连播</Label>
                <div className="text-xs text-muted-foreground">每轮 Agent 发言后自动继续</div>
              </div>
              <Switch id="autoplay" checked={autoPlay} onCheckedChange={setAutoPlay} />
            </div>
            {mode === "pipeline" && (
              <div className="text-xs text-muted-foreground">
                流水线模式按固定顺序依次执行一轮，用户插话可重新触发。
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t pt-4">
          <div className="truncate font-mono text-[9px] uppercase tracking-[0.08em] text-muted-foreground">
            预计 {mode === "pipeline" ? 5 : mode === "debate" ? maxRounds * 2 + 1 : maxRounds * 5 + 3} 发言
            · IN: {topic.trim() ? topic.trim() : "—"}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button onClick={() => void submit()} disabled={!topic.trim() || submitting}>
              {submitting && <Loader2 className="animate-spin" />}
              创建并进入会议
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
