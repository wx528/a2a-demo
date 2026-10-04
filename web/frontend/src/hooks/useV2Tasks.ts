import { useCallback, useEffect, useState } from "react"
import { listTasks, type V2TaskSummaryT } from "@/lib/v2api"

export function useV2Tasks(refreshMs = 15000) {
  const [tasks, setTasks] = useState<V2TaskSummaryT[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    try {
      const data = await listTasks()
      setTasks(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载任务失败")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
    const timer = window.setInterval(() => {
      void reload()
    }, refreshMs)
    return () => window.clearInterval(timer)
  }, [reload, refreshMs])

  return { tasks, loading, error, reload }
}
