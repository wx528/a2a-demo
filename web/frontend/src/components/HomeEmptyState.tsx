import { Bot } from "lucide-react"
import { Button } from "@/components/ui/button"

export function HomeEmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border bg-card p-8 text-center shadow-sm">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <Bot className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-xl font-bold">A2A 多人会议室</h1>
        <p className="mt-2 text-sm text-muted-foreground">创建一个主题，邀请多个 Agent 一起讨论</p>
        <Button className="mt-6" onClick={onCreate}>
          新建会议
        </Button>
      </div>
    </div>
  )
}
