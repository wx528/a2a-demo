import type { Meeting, MeetingMode } from "@/types"

export function modeBadgeText(mode: MeetingMode, maxRounds: number): string {
  if (mode === "roundtable") return `圆桌 · ${maxRounds}轮`
  if (mode === "debate") return `辩论 · ${maxRounds}轮`
  return "流水线"
}

export function modeBadgeTextFull(meeting: Pick<Meeting, "mode" | "max_rounds" | "auto_play">): string {
  if (meeting.mode === "roundtable") return `圆桌讨论 · ${meeting.max_rounds} 轮`
  if (meeting.mode === "debate") {
    return `辩论 · ${meeting.max_rounds} 轮 · ${meeting.auto_play ? "自动" : "步进"}`
  }
  return "流水线"
}
