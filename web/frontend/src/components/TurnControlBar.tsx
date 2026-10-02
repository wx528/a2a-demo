import { Loader2, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import type { TurnInfo } from "@/types"

export function TurnControlBar({
  turnInfo,
  turnRunning,
  autoPlay,
  onToggleAutoPlay,
  onContinue,
}: {
  turnInfo: TurnInfo | null
  turnRunning: boolean
  autoPlay: boolean
  onToggleAutoPlay: (value: boolean) => void
  onContinue: () => void
}) {
  if (!turnInfo || turnInfo.done || !turnInfo.next) return null

  return (
    <div className="border-b bg-primary/5 px-6 py-2">
      <div className="mx-auto flex max-w-4xl items-center gap-3 text-sm">
        <span className="font-medium">
          下一位发言：{turnInfo.next.avatar} {turnInfo.next.name}
        </span>
        <Button size="sm" onClick={onContinue} disabled={turnRunning}>
          {turnRunning ? <Loader2 className="animate-spin" /> : <Play />}
          继续
        </Button>
        <div className="ml-auto flex items-center gap-2">
          <Label htmlFor="autoplay-bar" className="text-xs text-muted-foreground">
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
      </div>
    </div>
  )
}
