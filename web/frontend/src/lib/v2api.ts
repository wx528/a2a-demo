export type GoalTypeT = "decision" | "research" | "compare" | "review"

export type TaskStatusT =
  | "preparing"
  | "running"
  | "waiting_confirmation"
  | "paused"
  | "completed"
  | "failed"

export type StageT = "clarify" | "compare" | "review" | "recommend"

export type AdvancedModeT = "pipeline" | "roundtable" | "debate"

export type InterventionIntentT = "追问" | "补充条件" | "调整方向"

export interface MaterialT {
  name: string
  text: string
}

export interface ConstraintT {
  text: string
  confirmed: boolean
}

export interface DecisionOptionT {
  id: string
  label: string
  impact: string
  recommended: boolean
  uncertain: boolean
}

export interface DecisionT {
  id: string
  round: number
  question: string
  options: DecisionOptionT[]
  chosen_id: string | null
  status: "open" | "resolved"
}

export interface TurnT {
  id: string
  seq: number
  stage: StageT
  author: string
  kind: "statement" | "user_note" | "decision_record" | "system"
  title: string
  body: string
  verified: boolean
  intent: string | null
}

export type OutcomeT = {
  conclusion?: string
  label?: "draft" | "ai_suggestion" | "team_confirmed"
  summary_groups?: {
    confirmed?: string[]
    disputed?: string[]
    unverified?: string[]
  }
  reasons?: { title?: string; body?: string; refs?: number[] }[]
  path_comparison?: {
    name?: string
    desc?: string
    pros?: string[]
    cons?: string[]
    fit?: string
    recommended?: boolean
  }[]
  evidence?: { seq_ref?: number; stage?: StageT; author?: string; quote?: string }[]
  open_questions?: string[]
  actions?: { title?: string; detail?: string; assignee?: string; due?: string }[]
  acceptance?: { title?: string; detail?: string }[]
} & Record<string, unknown>

export interface V2TaskT {
  id: string
  goal_type: string
  goal_text: string
  expected_outcome: string
  constraints: ConstraintT[]
  materials: MaterialT[]
  advanced_mode: AdvancedModeT
  advanced_rounds: number
  status: TaskStatusT
  current_stage: StageT
  stage_index: number
  turns: TurnT[]
  decisions: DecisionT[]
  outcome: OutcomeT | null
  demo: boolean
  error: string | null
  created_at: number
  updated_at: number
  connections: Record<string, string>
}

export interface V2TaskSummaryT {
  id: string
  goal_text: string
  status: TaskStatusT
  current_stage: StageT
  demo: boolean
  outcome_summary: string
  created_at: number
}

export interface CreateTaskBodyT {
  goal_type?: GoalTypeT
  goal_text: string
  expected_outcome?: string
  constraints?: string[]
  materials?: MaterialT[]
  advanced_mode?: AdvancedModeT
  advanced_rounds?: number
}

export interface StartTaskBodyT {
  constraints?: string[]
  advanced_mode?: AdvancedModeT
  advanced_rounds?: number
}

export type OutcomePatchT = {
  conclusion?: string
  summary_groups?: NonNullable<OutcomeT["summary_groups"]>
  reasons?: NonNullable<OutcomeT["reasons"]>
  path_comparison?: NonNullable<OutcomeT["path_comparison"]>
  evidence?: NonNullable<OutcomeT["evidence"]>
  open_questions?: string[]
  actions?: NonNullable<OutcomeT["actions"]>
  acceptance?: NonNullable<OutcomeT["acceptance"]>
}

const BASE = "/api/v2"

async function parseErrorDetail(resp: Response): Promise<string> {
  const data: unknown = await resp.json().catch(() => null)
  if (data !== null && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === "string") return detail
  }
  return `请求失败（${resp.status}）`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init)
  if (!resp.ok) throw new Error(await parseErrorDetail(resp))
  return (await resp.json()) as T
}

function jsonRequest<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  })
}

export function listTasks(): Promise<V2TaskSummaryT[]> {
  return request<V2TaskSummaryT[]>("/tasks")
}

export function getTask(id: string): Promise<V2TaskT> {
  return request<V2TaskT>(`/tasks/${id}`)
}

export function createTask(body: CreateTaskBodyT): Promise<V2TaskT> {
  return jsonRequest<V2TaskT>("/tasks", "POST", body)
}

export function startTask(id: string, body?: StartTaskBodyT): Promise<V2TaskT> {
  return jsonRequest<V2TaskT>(`/tasks/${id}/start`, "POST", body)
}

export function submitDecision(
  id: string,
  decisionId: string,
  optionId: string,
): Promise<V2TaskT> {
  return jsonRequest<V2TaskT>(`/tasks/${id}/decisions/${decisionId}`, "POST", {
    option_id: optionId,
  })
}

export function sendIntervention(
  id: string,
  intent: InterventionIntentT,
  text: string,
): Promise<Record<string, unknown>> {
  return jsonRequest<Record<string, unknown>>(`/tasks/${id}/interventions`, "POST", {
    intent,
    text,
  })
}

export function pauseTask(id: string): Promise<V2TaskT> {
  return jsonRequest<V2TaskT>(`/tasks/${id}/pause`, "POST")
}

export function resumeTask(id: string): Promise<V2TaskT> {
  return jsonRequest<V2TaskT>(`/tasks/${id}/resume`, "POST")
}

export function retryTask(id: string): Promise<V2TaskT> {
  return jsonRequest<V2TaskT>(`/tasks/${id}/retry`, "POST")
}

export function endTask(id: string): Promise<V2TaskT> {
  return jsonRequest<V2TaskT>(`/tasks/${id}/end`, "POST")
}

export function getOutcome(id: string): Promise<OutcomeT> {
  return request<OutcomeT>(`/tasks/${id}/outcome`)
}

export function patchOutcome(id: string, partial: OutcomePatchT): Promise<OutcomeT> {
  return jsonRequest<OutcomeT>(`/tasks/${id}/outcome`, "PATCH", partial)
}

export function confirmOutcome(id: string): Promise<OutcomeT> {
  return jsonRequest<OutcomeT>(`/tasks/${id}/outcome/confirm`, "POST")
}

export function exportUrl(id: string): string {
  return `${BASE}/tasks/${id}/export`
}

export function streamUrl(id: string): string {
  return `${BASE}/tasks/${id}/stream`
}
