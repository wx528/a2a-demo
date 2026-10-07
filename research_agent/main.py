"""
Research Agent - A2A 合规示例（JSON-RPC 2.0 绑定）
能力：接收一个主题，返回该主题的研究摘要
"""

import os
import sys
from typing import Iterator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env
load_env()
from shared.a2a_server import A2AJSONRPCServer, InMemoryTaskStore, collect_user_text
from shared.models import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Task,
    TaskState,
)
from shared.llm_client import call_llm
from shared.search_tool import web_search
from shared.agent_loop import agentic_stream
from shared.task_store import SqliteTaskStore


AGENT_PORT = int(os.getenv("PORT", 8001))
AGENT_HOST = os.getenv("HOST", "localhost")
BIND_HOST = os.getenv("BIND_HOST", "127.0.0.1")  # 监听接口：本地默认只听回环，容器经 BIND_HOST=0.0.0.0 显式放开
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


def stream_response(task: Task, store: InMemoryTaskStore) -> Iterator[str]:
    """流式版本：检索 → 起草 → 自审 → 修订，中间阶段以 <think> 包裹。"""
    user_text = collect_user_text(task)
    fallback = "（当前 LLM 服务不可用，无法生成回答。）"

    yield "[PHASE] 检索资料"
    search_context = ""
    try:
        sources = web_search(user_text[:80], max_results=4)
        if sources:
            lines = [
                f"[资料{i}] {s.get('title', '')}\n摘要: {s.get('snippet', '')}"
                for i, s in enumerate(sources, 1)
            ]
            search_context = "检索资料：\n" + "\n\n".join(lines)
    except Exception:
        search_context = ""  # 检索失败不阻塞发言

    yield from agentic_stream(
        DEFAULT_SYSTEM_PROMPT, user_text, search_context=search_context, fallback=fallback
    )


def process_task(task: Task, store: InMemoryTaskStore):
    """研究 Agent 的核心处理逻辑。"""
    store.update_status(task, TaskState.WORKING, "正在研究...")

    response = generate_response(collect_user_text(task))
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

    uvicorn.run(app, host=BIND_HOST, port=AGENT_PORT)
