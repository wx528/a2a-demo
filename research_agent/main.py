"""
Research Agent - A2A 合规示例（JSON-RPC 2.0 绑定）
能力：接收一个主题，返回该主题的研究摘要
"""

import os
import sys
from typing import Iterator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.a2a_server import A2AJSONRPCServer, InMemoryTaskStore
from shared.models import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Role,
    Task,
    TaskState,
)
from shared.llm_client import call_llm, call_llm_stream
from shared.task_store import SqliteTaskStore


AGENT_PORT = int(os.getenv("PORT", 8001))
AGENT_HOST = os.getenv("HOST", "localhost")
# 可通过 AGENT_URL 覆盖 Agent Card 中对外暴露的 URL（例如公网地址、Docker 外部地址）
AGENT_URL = os.getenv("AGENT_URL", f"http://{AGENT_HOST}:{AGENT_PORT}")


DEFAULT_SYSTEM_PROMPT = (
    "你是一名全能的技术助手。请严格按照用户的指令回答问题。"
    "直接输出最终答案，不要输出思考过程。"
)


def generate_response(user_text: str) -> str:
    """调用 LLM 直接回答用户输入；LLM 不可用时给出友好回退。"""
    llm_result = call_llm(DEFAULT_SYSTEM_PROMPT, user_text)
    if llm_result:
        return llm_result.split("</think>")[-1].strip()

    return "（当前 LLM 服务不可用，无法生成回答。）"


def _collect_user_text(task: Task) -> str:
    user_text = ""
    for msg in task.history:
        if msg.role == Role.USER:
            for part in msg.parts:
                if part.text:
                    user_text += part.text
    return user_text


def stream_response(task: Task, store: InMemoryTaskStore) -> Iterator[str]:
    """流式版本：增量产出 LLM token；LLM 不可用时整段回退。

    注意：流中途抛出的异常直接上抛，由框架将任务标记为 TASK_STATE_FAILED，
    不得静默截断（否则任务会带着不完整输出假装完成）。
    """
    user_text = _collect_user_text(task)
    deltas = call_llm_stream(DEFAULT_SYSTEM_PROMPT, user_text)
    fallback = "（当前 LLM 服务不可用，无法生成回答。）"
    if deltas is None:
        yield fallback
        return

    emitted = False
    for delta in deltas:
        if delta:
            emitted = True
            yield delta
    if not emitted:
        yield fallback


def process_task(task: Task, store: InMemoryTaskStore):
    """研究 Agent 的核心处理逻辑。"""
    store.update_status(task, TaskState.WORKING, "正在研究...")

    response = generate_response(_collect_user_text(task))
    store.add_artifact(task, "response", response, "text/markdown")
    store.update_status(task, TaskState.COMPLETED, "研究完成")


agent_card = AgentCard(
    name="research-agent",
    description="研究型 Agent，接收主题并返回研究摘要",
    supported_interfaces=[
        AgentInterface(
            url=f"{AGENT_URL}/rpc",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )
    ],
    version="1.0.0",
    capabilities=AgentCapabilities(
        streaming=True,
        push_notifications=False,
        extended_agent_card=False,
    ),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain", "text/markdown"],
    skills=[
        AgentSkill(
            id="research",
            name="主题研究",
            description="对给定主题进行快速研究并生成摘要",
            tags=["research", "summary"],
            examples=["研究 Kubernetes", "研究 A2A 协议"],
            input_modes=["text/plain"],
            output_modes=["text/plain", "text/markdown"],
        )
    ],
)


# 设置 TASK_DB 时启用 SQLite 任务持久化（如 /data/tasks.db），否则内存存储
TASK_DB = os.getenv("TASK_DB")
_task_store = SqliteTaskStore(TASK_DB) if TASK_DB else None


server = A2AJSONRPCServer(
    agent_card=agent_card,
    process_task=process_task,
    process_task_stream=stream_response,
    store=_task_store,
)
app = server.build_app(title="Research Agent (A2A / JSON-RPC)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
