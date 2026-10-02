import type { Meeting, MeetingMode } from "@/types"

export type SlotState = "done" | "current" | "pending"

export interface SlotView {
  kind: "agent" | "debate" | "judge" | "fallback"
  key: string
  participantId: string
  index: number
  state: SlotState
}

export interface ProgressView {
  slots: SlotView[]
  round: { current: number; total: number } | null
}

interface SeqSpec {
  kind: "agent" | "debate" | "judge" | "fallback"
  key: string
  index: number
}

const PIPELINE_STEPS = ["research", "writing", "review", "code", "summary"]
const ROUNDTABLE_AGENTS = ["research", "writing", "review", "code", "summary"]

export function buildSequence(
  mode: MeetingMode,
  maxRounds: number,
): SeqSpec[] {
  const seq: SeqSpec[] = []
  let index = 0
  const push = (kind: SeqSpec["kind"], key: string) => {
    seq.push({ kind, key, index })
    index += 1
  }
  if (mode === "roundtable") {
    push("agent", "moderator")
    for (let r = 0; r < Math.max(1, maxRounds); r += 1) {
      for (const k of ROUNDTABLE_AGENTS) push("agent", k)
    }
    push("fallback", "research")
    push("agent", "moderator")
    return seq
  }
  if (mode === "debate") {
    for (let r = 0; r < Math.max(1, maxRounds); r += 1) {
      push("debate", "pro")
      push("debate", "con")
    }
    push("judge", "judge")
    return seq
  }
  for (const k of PIPELINE_STEPS) push("agent", k)
  return seq
}

function toParticipantId(meeting: Meeting, key: string): string {
  if (key === "pro") return meeting.pro_persona
  if (key === "con") return meeting.con_persona
  return key
}

export function buildProgress(meeting: Meeting, seqIndexOverride?: number): ProgressView {
  const seq = buildSequence(meeting.mode, meeting.max_rounds)
  const seqIndex = Math.max(
    0,
    Math.round(seqIndexOverride ?? Number(meeting.turn_state?.seq_index ?? 0)),
  )

  const slots: SlotView[] = seq.map((slot) => ({
    ...slot,
    participantId: toParticipantId(meeting, slot.key),
    state:
      slot.index < seqIndex ? "done" : slot.index === seqIndex ? "current" : "pending",
  }))

  const total = meeting.max_rounds
  let round: ProgressView["round"] = null
  if (meeting.mode === "roundtable" && seqIndex > 0 && seqIndex < seq.length - 1) {
    round = {
      current: Math.min(total, Math.floor((seqIndex - 1) / ROUNDTABLE_AGENTS.length) + 1),
      total,
    }
  } else if (meeting.mode === "debate") {
    if (seqIndex >= seq.length - 1) {
      round = { current: total, total }
    } else {
      round = { current: Math.min(total, Math.floor(seqIndex / 2) + 1), total }
    }
  }

  return { slots, round }
}
