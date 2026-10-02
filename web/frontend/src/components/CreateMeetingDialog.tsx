import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Meeting, MeetingMode, Persona } from "@/types"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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

const MODE_OPTIONS: ReadonlyArray<[MeetingMode, string, string]> = [
  ["pipeline", "流水线模式", "依次发言"],
  ["roundtable", "圆桌讨论", "Moderator 主持"],
  ["debate", "辩论模式", "人格对抗 + 裁判"],
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
      })
      setTopic("")
      setMaxRounds(1)
      setAutoPlay(false)
      onCreated(meeting)
    } catch {
      toast.error("创建会议失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建会议</DialogTitle>
          <DialogDescription>创建一个主题，邀请多个 Agent 一起讨论</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="topic">会议主题</Label>
            <Input
              id="topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void submit()}
              placeholder="输入会议主题，例如：A2A protocol"
            />
          </div>

          <div className="space-y-2">
            <Label>会议模式</Label>
            <RadioGroup value={mode} onValueChange={(v) => setMode(v as MeetingMode)} className="gap-2">
              {MODE_OPTIONS.map(([value, title, desc]) => (
                <Label
                  key={value}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 has-[[data-state=checked]]:border-primary"
                >
                  <RadioGroupItem value={value} className="mt-0.5" />
                  <span>
                    <span className="block font-medium">{title}</span>
                    <span className="block text-xs font-normal text-muted-foreground">{desc}</span>
                  </span>
                </Label>
              ))}
            </RadioGroup>
          </div>

          {(mode === "roundtable" || mode === "debate") && (
            <div className="space-y-2">
              <Label>
                {mode === "debate" ? "辩论轮数" : "讨论轮数"}：{maxRounds} 轮
              </Label>
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
            <div className="grid grid-cols-2 gap-3">
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
            </div>
          )}

          <div className="flex items-center justify-between">
            <Label htmlFor="autoplay">自动连播</Label>
            <Switch id="autoplay" checked={autoPlay} onCheckedChange={setAutoPlay} />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => void submit()} disabled={!topic.trim() || submitting}>
            {submitting && <Loader2 className="animate-spin" />}
            创建会议室
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
