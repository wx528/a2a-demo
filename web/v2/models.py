from typing import Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["preparing", "running", "waiting_confirmation", "paused", "completed", "failed"]
Stage = Literal["clarify", "compare", "review", "recommend"]

STAGES: list[Stage] = ["clarify", "compare", "review", "recommend"]
STAGE_LABELS: dict[Stage, str] = {
    "clarify": "澄清需求",
    "compare": "比较方案",
    "review": "评审风险",
    "recommend": "形成建议",
}


class Material(BaseModel):
    name: str
    text: str = ""


class Constraint(BaseModel):
    text: str
    confirmed: bool = False


class DecisionOption(BaseModel):
    id: str
    label: str
    impact: str
    recommended: bool = False
    uncertain: bool = False


class Decision(BaseModel):
    id: str
    round: int = 1
    question: str
    options: list[DecisionOption]
    chosen_id: str | None = None
    status: Literal["open", "resolved"] = "open"


class Turn(BaseModel):
    id: str
    seq: int
    stage: Stage
    author: str
    kind: Literal["statement", "user_note", "decision_record", "system"]
    title: str = ""
    body: str = ""
    verified: bool = False
    intent: str | None = None


class SummaryGroups(BaseModel):
    confirmed: list[str] = Field(default_factory=list)
    disputed: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)


class Reason(BaseModel):
    title: str = ""
    body: str = ""
    refs: list[int] = Field(default_factory=list)


class PathOption(BaseModel):
    name: str = ""
    desc: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    fit: str = ""
    recommended: bool = False


class EvidenceItem(BaseModel):
    seq_ref: int = 0
    stage: Stage = "clarify"
    author: str = ""
    quote: str = ""


class ActionItem(BaseModel):
    title: str = ""
    detail: str = ""
    assignee: str = "待分配"
    due: str = "待确定"


class AcceptanceItem(BaseModel):
    title: str = ""
    detail: str = ""


class OutcomeDoc(BaseModel):
    conclusion: str = ""
    summary_groups: SummaryGroups = Field(default_factory=SummaryGroups)
    reasons: list[Reason] = Field(default_factory=list)
    path_comparison: list[PathOption] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)
    acceptance: list[AcceptanceItem] = Field(default_factory=list)
    label: Literal["draft", "ai_suggestion", "team_confirmed"] = "ai_suggestion"


class TaskExpert(BaseModel):
    id: str
    name: str
    url: str
    purpose: Literal["research", "propose", "challenge", "synthesize"]
    emoji: str = "🔌"
    source: Literal["builtin", "custom"] = "custom"


class V2Task(BaseModel):
    id: str
    goal_type: Literal["decision"] = "decision"
    goal_text: str
    expected_outcome: str = ""
    constraints: list[Constraint] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    advanced_mode: Literal["pipeline", "roundtable", "debate"] = "pipeline"
    advanced_rounds: int = 2
    experts: list[TaskExpert] = Field(default_factory=list)
    assignments: dict[str, str] = Field(default_factory=dict)
    status: TaskStatus = "preparing"
    current_stage: Stage = "clarify"
    stage_index: int = 0
    turns: list[Turn] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    outcome: OutcomeDoc | None = None
    demo: bool = False
    error: str | None = None
    created_at: float
    updated_at: float

    def next_seq(self) -> int:
        return max((t.seq for t in self.turns), default=0) + 1

    def expert_by_id(self, expert_id: str) -> TaskExpert | None:
        return next((e for e in self.experts if e.id == expert_id), None)

    def public_dict(self) -> dict:
        data = self.model_dump()
        data["connections"] = {}
        return data
