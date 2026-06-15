"""
A2A (Agent-to-Agent) 协议核心数据模型
参考: https://google.github.io/A2A/
"""

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
from enum import Enum


class TaskStatus(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TextPart(BaseModel):
    type: str = "text"
    text: str


class FilePart(BaseModel):
    type: str = "file"
    file: Dict[str, Any]


class DataPart(BaseModel):
    type: str = "data"
    data: Dict[str, Any]


Part = Union[TextPart, FilePart, DataPart]


class Message(BaseModel):
    role: str  # "user" | "agent"
    parts: List[Part]


class Artifact(BaseModel):
    name: Optional[str] = None
    parts: List[Part]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Task(BaseModel):
    id: str
    sessionId: str
    status: TaskStatus
    messages: List[Message]
    artifacts: List[Artifact] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    history: List[Message] = Field(default_factory=list)


class TaskSendParams(BaseModel):
    id: Optional[str] = None
    sessionId: Optional[str] = None
    message: Message
    acceptedOutputModes: Optional[List[str]] = None
    pushNotification: Optional[Dict[str, Any]] = None
    historyLength: Optional[int] = None


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    examples: List[str] = Field(default_factory=list)
    inputModes: Optional[List[str]] = None
    outputModes: Optional[List[str]] = None


class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = False


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str
    authentication: Optional[Dict[str, Any]] = None
    defaultInputModes: List[str]
    defaultOutputModes: List[str]
    capabilities: AgentCapabilities
    skills: List[AgentSkill]
