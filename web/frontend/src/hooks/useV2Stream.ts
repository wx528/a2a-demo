import { useCallback, useEffect, useRef, useState } from "react"
import {
  getTask,
  streamUrl,
  type StageT,
  type TaskStatusT,
  type TurnT,
  type V2TaskT,
} from "@/lib/v2api"
import { STAGE_ORDER } from "@/lib/roles"

export type V2TurnT = TurnT & { live?: boolean }
export type V2StreamTaskT = Omit<V2TaskT, "turns"> & { turns: V2TurnT[] }

type DeltaPayloadT = { author?: unknown; delta?: unknown }
type StatusPayloadT = { status?: TaskStatusT }
type StagePayloadT = { stage?: StageT }

function parsePayload<T>(event: MessageEvent): T | null {
  try {
    return JSON.parse(event.data as string) as T
  } catch {
    return null
  }
}

export function useV2Stream(taskId: string | null) {
  const [task, setTask] = useState<V2StreamTaskT | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [focusSeq, setFocusSeq] = useState<number | null>(null)
  const taskRef = useRef<V2StreamTaskT | null>(null)
  const closedRef = useRef<Set<string>>(new Set())
  const refreshSeqRef = useRef(0)

  const update = useCallback((next: V2StreamTaskT | null) => {
    taskRef.current = next
    setTask(next)
  }, [])

  useEffect(() => {
    const raw = sessionStorage.getItem("v2FocusTurn")
    if (raw === null) return
    sessionStorage.removeItem("v2FocusTurn")
    const seq = Number.parseInt(raw, 10)
    if (Number.isFinite(seq)) setFocusSeq(seq)
  }, [])

  const applyRefresh = useCallback(
    async (id: string) => {
      const token = ++refreshSeqRef.current
      try {
        const fresh = await getTask(id)
        if (token !== refreshSeqRef.current) return
        const prev = taskRef.current
        if (prev && prev.id !== id) return
        const pending =
          prev && prev.id === fresh.id
            ? prev.turns.filter((turn) => turn.live && !closedRef.current.has(turn.id))
            : []
        update(pending.length > 0 ? { ...fresh, turns: [...fresh.turns, ...pending] } : fresh)
      } catch {
        // 保留当前视图，等待下一次事件或重连快照
      }
    },
    [update],
  )

  const refresh = useCallback(() => {
    if (taskId) void applyRefresh(taskId)
  }, [taskId, applyRefresh])

  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    closedRef.current = new Set()
    update(null)
    setError(null)
    setConnected(false)

    getTask(taskId)
      .then((data) => {
        if (cancelled) return
        // 竞态保护：HTTP 快照可能晚于一条更及时的 SSE init，旧快照直接丢弃
        const prev = taskRef.current
        if (prev && prev.id === data.id && prev.updated_at >= data.updated_at) return
        update(data)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "加载任务失败")
      })

    const source = new EventSource(streamUrl(taskId))
    source.onopen = () => {
      if (!cancelled) setConnected(true)
    }
    source.onerror = () => {
      // EventSource 自动重连；重连后的 init 快照会整体替换状态
      if (!cancelled) setConnected(false)
    }

    source.addEventListener("init", (event) => {
      if (cancelled) return
      const data = parsePayload<V2TaskT>(event)
      if (!data) return
      // SSE init 快照不带探活结果；已有连接状态时保留，避免会议舱误报 0/4 在线
      const prev = taskRef.current
      const hasConnections = Object.keys(data.connections ?? {}).length > 0
      if (prev && prev.id === data.id && !hasConnections) {
        update({ ...data, connections: prev.connections })
        return
      }
      update(data)
    })

    source.addEventListener("status_change", (event) => {
      if (cancelled) return
      const data = parsePayload<StatusPayloadT>(event)
      if (!data?.status) return
      const prev = taskRef.current
      if (!prev) return
      if (data.status === "failed") {
        // 中止的流式发言不落库：关闭 live turn 并移除残文，让重试从干净状态开始
        for (const turn of prev.turns) {
          if (turn.live) closedRef.current.add(turn.id)
        }
        update({ ...prev, status: data.status, turns: prev.turns.filter((turn) => !turn.live) })
        return
      }
      update({ ...prev, status: data.status })
    })

    source.addEventListener("stage_change", (event) => {
      if (cancelled) return
      const data = parsePayload<StagePayloadT>(event)
      if (!data?.stage) return
      const prev = taskRef.current
      if (!prev) return
      const index = STAGE_ORDER.indexOf(data.stage)
      update({
        ...prev,
        current_stage: data.stage,
        stage_index: index >= 0 ? index : prev.stage_index,
      })
    })

    source.addEventListener("turn_delta", (event) => {
      if (cancelled) return
      const data = parsePayload<DeltaPayloadT>(event)
      if (!data || typeof data.author !== "string" || typeof data.delta !== "string") return
      const prev = taskRef.current
      if (!prev) return
      const turns = [...prev.turns]
      let appended = false
      for (let i = turns.length - 1; i >= 0; i--) {
        const turn = turns[i]
        if (turn.author === data.author && turn.kind === "statement") {
          if (turn.live && !closedRef.current.has(turn.id)) {
            turns[i] = { ...turn, body: turn.body + data.delta }
            appended = true
          }
          break
        }
      }
      if (appended) {
        update({ ...prev, turns })
        return
      }
      const liveTurn: V2TurnT = {
        id: `live-${data.author}-${Date.now()}`,
        seq: -1,
        stage: prev.current_stage,
        author: data.author,
        kind: "statement",
        title: "",
        body: data.delta,
        verified: false,
        intent: null,
        live: true,
      }
      update({ ...prev, turns: [...turns, liveTurn] })
    })

    source.addEventListener("turn_done", () => {
      if (cancelled) return
      const prev = taskRef.current
      if (prev) {
        for (const turn of prev.turns) {
          if (turn.live) closedRef.current.add(turn.id)
        }
      }
      void applyRefresh(taskId)
    })

    source.addEventListener("decision_required", () => {
      if (cancelled) return
      void applyRefresh(taskId)
    })

    source.addEventListener("intervention_ack", () => {
      if (cancelled) return
      // 行内 ack 已即时反馈，这里只刷新落库结果，不再重复 toast
      void applyRefresh(taskId)
    })

    source.addEventListener("outcome_update", () => {
      if (cancelled) return
      void applyRefresh(taskId)
    })

    return () => {
      cancelled = true
      source.close()
    }
  }, [taskId, update, applyRefresh])

  return { task, connected, error, focusSeq, refresh }
}
