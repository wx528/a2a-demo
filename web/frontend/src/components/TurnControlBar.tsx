import { Loader2, Play, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import type { ProgressView } from "@/lib/sequence"
import type { TurnInfo } from "@/types"

export function TurnControlBar({
  turnInfo,
  turnRunning,
  autoPlay,
  progress,
  onToggleAutoPlay,
  onContinue,
}: {
  turnInfo: TurnInfo | null
  turnRunning: boolean
  autoPlay: boolean
  progress: ProgressView
  onToggleAutoPlay: (value: boolean) => void
  onContinue: () => void
}) {
  if (!turnInfo || turnInfo.done || !turnInfo.next) return null

  const roundLabel = progress.round ? ` · ROUND ${progress.round.current}/${progress.round.total}` : ""

  return (
    <div className="border-y border-dashed border-primary/40 bg-primary/5 px-6 py-3">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] bg-primary text-primary-foreground shadow-glow">
          <Zap className="h-5 w-5" />
        </div>
        <div className="min-w-0 leading-tight">
          <div className="font-mono text-[9px] uppercase tracking-[0.08em] text-assist">
            NEXT SPEAKER{roundLabel}
          </div>
          <div className="mt-0.5 truncate text-base font-bold">
            下一位发言：{turnInfo.next.avatar} {turnInfo.next.name}
          </div>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-4">
          <div className="flex items-center gap-2">
            <Label htmlFor="autoplay-bar" className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
              自动连播
            </Label>
            <Switch
              id="autoplay-bar"
              checked={autoPlay}
              onCheckedChange={(v) => {
                onToggleAutoPlay(v)
                if (v && !turnRunning) onContinue()
              }}
            />
          </div>
          <Button className="shadow-glow" onClick={onContinue} disabled={turnRunning}>
            {turnRunning ? <Loader2 className="animate-spin" /> : <Play />}
            继续
          </Button>
        </div>
      </div>
    </div>
  )
}
