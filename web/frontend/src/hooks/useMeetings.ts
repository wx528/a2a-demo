import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { MeetingSummary } from "@/types"

export function useMeetings() {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([])

  const refresh = useCallback(async () => {
    try {
      setMeetings(await api.listMeetings())
    } catch {
      toast.error("加载会议列表失败")
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const remove = useCallback(async (id: string) => {
    try {
      await api.deleteMeeting(id)
      setMeetings((prev) => prev.filter((m) => m.id !== id))
      toast.success("会议已删除")
      return true
    } catch {
      toast.error("删除会议失败")
      return false
    }
  }, [])

  return { meetings, refresh, remove }
}
