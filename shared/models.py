"""
A2A (Agent-to-Agent) 协议核心数据模型
参考: https://a2a-protocol.org/latest/specification/
使用 Pydantic v2，字段别名统一为 camelCase 以匹配官方 JSON 规范。
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _to_camel(snake: str) -> str:
    """将 snake_case 转为 camelCase。"""
    parts = snake.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


# ---------------------------------------------------------------------------
# 基础类型
# ---------------------------------------------------------------------------


class TaskState(str, Enum):
    """A2A Task 生命周期状态。"""
    UNSPECIFIED = "unspecified"
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    INPUT_REQUIRED = "input-required"
    REJECTED = "rejected"
    AUTH_REQUIRED = "auth-required"


class Role(str, Enum):
    """消息发送者角色。"""
    UNSPECIFIED = "unspecified"
    USER = "user"
    AGENT = "agent"


# ---------------------------------------------------------------------------
# Part / Message / Artifact
# ---------------------------------------------------------------------------


class Part(BaseModel):
    """
    A2A 内容单元。
    规范中为 oneof {text, raw, url, data}，这里以可选字段呈现，并校验至少有一项。
    """
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    text: Optional[str] = None
    raw: Optional[str] = None  # JSON 中以 base64 字符串传输
    url: Optional[str] = None
    data: Optional[Any] = None  # 任意 JSON 值
    metadata: Optional[Dict[str, Any]] = None
    filename: Optional[str] = None
    media_type: Optional[str] = None

    @model_validator(mode="after")
    def check_one_content(self):
        fields = [self.text, self.raw, self.url, self.data]
        present = [f for f in fields if f is not None]
        if len(present) == 0:
            raise ValueError("Part 必须包含 text/raw/url/data 中至少一项")
        return self


class Message(BaseModel):
    """一次通信回合。"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    message_id: str
    context_id: Optional[str] = None
    task_id: Optional[str] = None
    role: Role
    parts: List[Part]
    metadata: Optional[Dict[str, Any]] = None
    extensions: Optional[List[str]] = None
    reference_task_ids: Optional[List[str]] = None


class Artifact(BaseModel):
    """任务输出产物。"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    artifact_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    parts: List[Part]
    metadata: Optional[Dict[str, Any]] = None
    extensions: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Task / TaskStatus / Events
# ---------------------------------------------------------------------------


class TaskStatus(BaseModel):
    """任务状态容器。"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    state: TaskState
    message: Optional[Message] = None
    timestamp: Optional[str] = None


class Task(BaseModel):
    """A2A 核心工作单元。"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    id: str
    context_id: Optional[str] = None
    status: TaskStatus
    artifacts: Optional[List[Artifact]] = Field(default_factory=list)
    history: Optional[List[Message]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class TaskStatusUpdateEvent(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    task_id: str
    context_id: Optional[str] = None
    status: TaskStatus
    metadata: Optional[Dict[str, Any]] = None


class TaskArtifactUpdateEvent(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    task_id: str
    context_id: Optional[str] = None
    artifact: Artifact
    append: Optional[bool] = False
    last_chunk: Optional[bool] = False
    metadata: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------


class AgentInterface(BaseModel):
    """Agent 暴露的接口描述。"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    url: str
    protocol_binding: str  # e.g. "JSONRPC", "HTTP+JSON", "GRPC"
    protocol_version: str  # e.g. "1.0"
    tenant: Optional[str] = None


class AgentProvider(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    url: str
    organization: str


class AgentExtension(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    uri: str
    description: Optional[str] = None
    required: Optional[bool] = False
    params: Optional[Dict[str, Any]] = None


class AgentCapabilities(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    streaming: Optional[bool] = False
    push_notifications: Optional[bool] = False
    extended_agent_card: Optional[bool] = False
    extensions: Optional[List[AgentExtension]] = Field(default_factory=list)


class AgentSkill(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    id: str
    name: str
    description: str
    tags: Optional[List[str]] = Field(default_factory=list)
    examples: Optional[List[str]] = Field(default_factory=list)
    input_modes: Optional[List[str]] = None
    output_modes: Optional[List[str]] = None
    security_requirements: Optional[List["SecurityRequirement"]] = None


class SecurityRequirement(BaseModel):
    """安全需求占位，可后续扩展。"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    schemes: Optional[Dict[str, List[str]]] = None


class AgentCardSignature(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    protected: str
    signature: str
    header: Optional[Dict[str, Any]] = None


class AgentCard(BaseModel):
    """Agent 自描述元数据。"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    name: str
    description: str
    supported_interfaces: List[AgentInterface]
    provider: Optional[AgentProvider] = None
    version: str
    documentation_url: Optional[str] = None
    capabilities: AgentCapabilities
    security_schemes: Optional[Dict[str, Any]] = None
    security_requirements: Optional[List[SecurityRequirement]] = None
    default_input_modes: List[str]
    default_output_modes: List[str]
    skills: List[AgentSkill]
    signatures: Optional[List[AgentCardSignature]] = None
    icon_url: Optional[str] = None


# ---------------------------------------------------------------------------
# 请求/响应参数对象
# ---------------------------------------------------------------------------


class SendMessageConfiguration(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    accepted_output_modes: Optional[List[str]] = None
    task_push_notification_config: Optional[Dict[str, Any]] = None
    history_length: Optional[int] = None
    return_immediately: Optional[bool] = False


class SendMessageRequest(BaseModel):
    """tasks/send 的请求参数。"""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tenant: Optional[str] = None
    message: Message
    configuration: Optional[SendMessageConfiguration] = None
    metadata: Optional[Dict[str, Any]] = None


class GetTaskRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tenant: Optional[str] = None
    id: str
    history_length: Optional[int] = None


class CancelTaskRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tenant: Optional[str] = None
    id: str
    metadata: Optional[Dict[str, Any]] = None


class ListTasksRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tenant: Optional[str] = None
    context_id: Optional[str] = None
    status: Optional[TaskState] = None
    page_size: Optional[int] = None
    page_token: Optional[str] = None
    history_length: Optional[int] = None
    status_timestamp_after: Optional[str] = None
    include_artifacts: Optional[bool] = False


class ListTasksResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tasks: List[Task]
    next_page_token: str
    page_size: int
    total_size: int


class SubscribeToTaskRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    tenant: Optional[str] = None
    id: str


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 基础类型
# ---------------------------------------------------------------------------


class JSONRPCRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Union[Dict[str, Any], List[Any]]] = None


class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None


class JSONRPCResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None


# ---------------------------------------------------------------------------
# StreamResponse（用于 streaming / SSE）
# ---------------------------------------------------------------------------


class StreamResponse(BaseModel):
    """
    流式响应包装器。规范中为 oneof {task, message, statusUpdate, artifactUpdate}。
    """
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    task: Optional[Task] = None
    message: Optional[Message] = None
    status_update: Optional[TaskStatusUpdateEvent] = None
    artifact_update: Optional[TaskArtifactUpdateEvent] = None


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    """返回 ISO 8601 UTC 时间字符串。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def text_part(text: str, media_type: str = "text/plain") -> Part:
    return Part(text=text, media_type=media_type)


def artifact_from_text(name: str, text: str, media_type: str = "text/plain") -> Artifact:
    return Artifact(
        artifact_id=str(uuid4()),
        name=name,
        parts=[text_part(text, media_type)],
    )


# ---------------------------------------------------------------------------
# 向后兼容别名（供旧版 web 会议室等未改造模块临时导入使用）
# ---------------------------------------------------------------------------

TextPart = Part
FilePart = Part
DataPart = Part
TaskSendParams = SendMessageRequest
