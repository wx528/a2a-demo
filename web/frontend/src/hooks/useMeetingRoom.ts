import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { createSseParser } from "@/lib/sse"
import type { ChatMessage, Meeting, Participant, TurnInfo } from "@/types"

export function useMeetingRoom(meetingId: string | null) {
  const [meeting, setMeeting] = useState<Meeting | null>(null)
  const [connected, setConnected] = useState(false)
  const [turnInfo, setTurnInfo] = useState<TurnInfo | null>(null)
  const [turnRunning, setTurnRunning] = useState(false)
  const [autoPlay, setAutoPlayState] = useState(false)

  const autoPlayRef = useRef(false)
  const runningRef = useRef(false)
  const retryRef = useRef(0)
  const reconnectTimer = useRef<number | null>(null)
  const evtSourceRef = useRef<EventSource | null>(null)
  const runNextTurnRef = useRef<() => Promise<void>>(async () => {})

  const setAutoPlay = useCallback((value: boolean) => {
    autoPlayRef.current = value
    setAutoPlayState(value)
  }, [])

  // SSE：init 快照 + 断线指数退避重连
  useEffect(() => {
    if (!meetingId) return
    let disposed = false

    const connect = () => {
      const es = new EventSource(`/api/meetings/${meetingId}/events`)
      evtSourceRef.current = es
      es.addEventListener("init", (e) => {
        if (disposed) return
        const wasReconnect = retryRef.current > 0
        const data = JSON.parse((e as MessageEvent).data) as Meeting
        setMeeting(data)
        setConnected(true)
        setAutoPlay(data.auto_play)
        retryRef.current = 0
        api.peekNextTurn(meetingId).then(setTurnInfo).catch(() => {})
        if (wasReconnect) toast.success("已恢复实时连接")
      })
      es.onerror = () => {
        if (disposed) return
        setConnected(false)
        es.close()
        const delay = Math.min(15000, 1000 * 2 ** retryRef.current)
        retryRef.current += 1
        if (retryRef.current === 1) toast.error("实时连接已断开，正在重连…")
        reconnectTimer.current = window.setTimeout(connect, delay)
      }
    }
    connect()

    return () => {
      disposed = true
      evtSourceRef.current?.close()
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current)
      setConnected(false)
      setMeeting(null)
      setTurnInfo(null)
      retryRef.current = 0
    }
  }, [meetingId, setAutoPlay])

  const applyTurnEvent = useCallback(
    (event: string, data: string) => {
      if (event === "message") {
        const msg = JSON.parse(data) as ChatMessage
        setMeeting((prev) => (prev ? { ...prev, messages: [...prev.messages, msg] } : prev))
      } else if (event === "system") {
        const { content } = JSON.parse(data) as { content: string }
        const msg: ChatMessage = {
          id: `sys-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          meeting_id: meetingId ?? "",
          participant_id: "system",
          participant_name: "系统",
          role: "system",
          content,
          timestamp: new Date().toLocaleTimeString(),
          type: "system",
        }
        setMeeting((prev) => (prev ? { ...prev, messages: [...prev.messages, msg] } : prev))
      } else if (event === "status") {
        const { participant_id, status } = JSON.parse(data) as {
          participant_id: string
          status: string
        }
        setMeeting((prev) =>
          prev
            ? {
                ...prev,
                participants: prev.participants.map((p) =>
                  p.id === participant_id ? { ...p, status: status as Participant["status"] } : p,
                ),
              }
            : prev,
        )
      }
    },
    [meetingId],
  )

  const runNextTurn = useCallback(async () => {
    if (!meetingId || runningRef.current) return
    runningRef.current = true
    setTurnRunning(true)
    try {
      const res = await fetch(`/api/meetings/${meetingId}/turns/next`, { method: "POST" })
      if (!res.ok || !res.body) throw new Error(`请求失败：${res.status}`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      const parser = createSseParser(({ event, data }) => {
        if (event === "turn_done") {
          const payload = JSON.parse(data) as TurnInfo
          setTurnInfo(payload)
          if (!payload.done && autoPlayRef.current) {
            window.setTimeout(() => void runNextTurnRef.current(), 600)
          }
        } else {
          applyTurnEvent(event, data)
        }
      })
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        parser.push(decoder.decode(value, { stream: true }))
      }
    } catch {
      toast.error("执行发言失败，请重试")
    } finally {
      runningRef.current = false
      setTurnRunning(false)
    }
  }, [meetingId, applyTurnEvent])
  runNextTurnRef.current = runNextTurn

  const sendMessage = useCallback(
    async (content: string) => {
      if (!meetingId || !content.trim()) return false
      try {
        const msg = await api.sendMessage(meetingId, content)
        setMeeting((prev) => (prev ? { ...prev, messages: [...prev.messages, msg] } : prev))
        void runNextTurnRef.current()
        return true
      } catch {
        toast.error("发送失败，请重试")
        return false
      }
    },
    [meetingId],
  )

  return {
    meeting,
    connected,
    turnInfo,
    turnRunning,
    autoPlay,
    setAutoPlay,
    runNextTurn,
    sendMessage,
  }
}
