"""
Writing Agent - A2A 合规示例（JSON-RPC 2.0 绑定）
能力：基于研究摘要，生成一篇格式化文章
"""

import os
import sys

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
from shared.task_store import SqliteTaskStore


AGENT_PORT = int(os.getenv("PORT", 8002))
AGENT_HOST = os.getenv("HOST", "localhost")
AGENT_URL = os.getenv("AGENT_URL", f"http://{AGENT_HOST}:{AGENT_PORT}")


DEFAULT_SYSTEM_PROMPT = (
    "你是一名全能的技术助手。请严格按照用户的指令回答问题。"
    "直接输出最终答案，不要输出思考过程。"
)


def generate_response(user_text: str) -> str:
    """调用 LLM 直接回答用户输入；LLM 不可用时给出友好回退。"""
    llm_result = call_llm(DEFAULT_SYSTEM_PROMPT, user_text, max_tokens=4000)
    if llm_result:
        return llm_result.split("</think>")[-1].strip()

    return "（当前 LLM 服务不可用，无法生成回答。）"


def process_task(task: Task, store: InMemoryTaskStore):
    """写作 Agent 的核心处理逻辑。"""
    store.update_status(task, TaskState.WORKING, "正在写作...")

    response = generate_response(collect_user_text(task))
    store.add_artifact(task, "response", response, "text/markdown")
    store.update_status(task, TaskState.COMPLETED, "写作完成")


agent_card = AgentCard(
    name="writing-agent",
    description="写作型 Agent，基于研究摘要生成格式化文章",
    supported_interfaces=[
        AgentInterface(
            url=f"{AGENT_URL}/rpc",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )
    ],
    version="1.0.0",
    capabilities=AgentCapabilities(
        streaming=False,
        push_notifications=False,
        extended_agent_card=False,
    ),
    default_input_modes=["text/plain", "text/markdown"],
    default_output_modes=["text/markdown"],
    skills=[
        AgentSkill(
            id="write-article",
            name="文章写作",
            description="根据已有素材生成 Markdown 格式文章",
            tags=["writing", "markdown"],
            examples=["根据 Kubernetes 摘要写文章"],
            input_modes=["text/plain", "text/markdown"],
            output_modes=["text/markdown"],
        )
    ],
)


# 设置 TASK_DB 时启用 SQLite 任务持久化（如 /data/tasks.db），否则内存存储
TASK_DB = os.getenv("TASK_DB")
_task_store = SqliteTaskStore(TASK_DB) if TASK_DB else None


server = A2AJSONRPCServer(
    agent_card=agent_card,
    process_task=process_task,
    store=_task_store,
)
app = server.build_app(title="Writing Agent (A2A / JSON-RPC)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
