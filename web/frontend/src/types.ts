export type MeetingMode = "pipeline" | "roundtable" | "debate"

export interface Participant {
  id: string
  name: string
  role: string
  avatar: string
  status: "idle" | "thinking" | "speaking"
  phase?: string
}

export interface ChatMessage {
  id: string
  meeting_id: string
  participant_id: string
  participant_name: string
  role: string
  content: string
  timestamp: string
  type: string // message | system | pass | judge | status
}

export interface Meeting {
  id: string
  topic: string
  mode: MeetingMode
  max_rounds: number
  auto_play: boolean
  pro_persona: string
  con_persona: string
  inquiry_enabled: boolean
  created_at: string
  participants: Participant[]
  messages: ChatMessage[]
  status: string
  turn_state?: { seq_index?: number; topic_override?: string }
}

export interface MeetingSummary {
  id: string
  topic: string
  mode: MeetingMode
  max_rounds: number
  created_at: string
  status: string
  auto_play: boolean
}

export interface Persona {
  id: string
  name: string
  style: string
  avatar: string
}

export interface TurnInfo {
  done: boolean
  next: { participant_id: string; name: string; avatar: string } | null
  mode?: MeetingMode
  auto_play?: boolean
  seq_index?: number
}
