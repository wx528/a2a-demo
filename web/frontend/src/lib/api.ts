import type {
  ChatMessage,
  Meeting,
  MeetingMode,
  MeetingSummary,
  Persona,
  TurnInfo,
} from "@/types"

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init)
  if (!res.ok) throw new Error(`请求失败：${res.status}`)
  return res.json() as Promise<T>
}

export interface CreateMeetingBody {
  topic: string
  mode: MeetingMode
  max_rounds: number
  auto_play: boolean
  pro_persona: string
  con_persona: string
  inquiry_enabled: boolean
}

export const api = {
  listMeetings: () => request<MeetingSummary[]>("/api/meetings"),

  getMeeting: (id: string) => request<Meeting>(`/api/meetings/${id}`),

  deleteMeeting: (id: string) =>
    request<{ deleted: boolean }>(`/api/meetings/${id}`, { method: "DELETE" }),

  createMeeting: (body: CreateMeetingBody) =>
    request<Meeting>("/api/meetings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  listPersonas: () => request<Persona[]>("/api/personas"),

  sendMessage: (meetingId: string, content: string) =>
    request<ChatMessage>(`/api/meetings/${meetingId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    }),

  peekNextTurn: (meetingId: string) =>
    request<TurnInfo>(`/api/meetings/${meetingId}/next-turn`),

  exportUrl: (meetingId: string) => `/api/meetings/${meetingId}/export`,

  suggestTopics: (count = 3, seed = "") =>
    request<{ topics: string[] }>("/api/topics/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count, seed }),
    }),

  previewViewpoints: (body: { topic: string; pro_persona: string; con_persona: string }) =>
    request<{ pro: string; con: string }>("/api/viewpoints/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
}
