import { Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Eyebrow } from "@/components/Eyebrow"

const FEATURES: ReadonlyArray<[string, string]> = [
  ["01", "顺序编排"],
  ["02", "实时插话"],
  ["03", "自动总结"],
]

export function HeroHome({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-xl rounded-[28px] border bg-card/80 p-10 text-center shadow-soft">
        <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-[20px] border border-primary/40 bg-primary/10 shadow-glow">
          <Sparkles className="h-7 w-7 text-primary" />
        </div>
        <Eyebrow>INITIALIZE MULTI-AGENT SESSION</Eyebrow>
        <h1 className="mt-3 text-4xl font-extrabold leading-[1.2] tracking-tight">
          让多个 AI Agent
          <br />
          围绕一个主题真正交锋
        </h1>
        <p className="mx-auto mt-4 max-w-md text-sm text-muted-foreground">
          选择流水线、圆桌或辩论模式，Agent 按秩序发言、互相回应，你可以随时插入观点或质询。
        </p>
        <Button size="lg" className="mt-7 gap-2" onClick={onCreate}>
          <Sparkles className="h-4 w-4" />
          发起第一次会议
        </Button>
        <div className="mt-8 grid grid-cols-3 gap-4 border-t pt-5">
          {FEATURES.map(([num, label]) => (
            <div key={num} className="text-center">
              <div className="font-mono text-[10px] text-muted-foreground">{num}</div>
              <div className="mt-1 text-xs text-foreground/80">{label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
