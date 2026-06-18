"""
Research Agent - A2A 合规示例（JSON-RPC 2.0 绑定）
能力：接收一个主题，返回该主题的研究摘要
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.a2a_server import A2AJSONRPCServer, InMemoryTaskStore
from shared.models import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Task,
    TaskState,
)
from shared.llm_client import call_llm


AGENT_PORT = int(os.getenv("PORT", 8001))
AGENT_HOST = os.getenv("HOST", "localhost")
# 可通过 AGENT_URL 覆盖 Agent Card 中对外暴露的 URL（例如公网地址、Docker 外部地址）
AGENT_URL = os.getenv("AGENT_URL", f"http://{AGENT_HOST}:{AGENT_PORT}")


# 模拟知识库
KNOWLEDGE_BASE = {
    "kubernetes": "Kubernetes 是一个开源的容器编排平台，由 Google 设计并捐赠给 CNCF。",
    "a2a": "A2A (Agent-to-Agent) 是 Google 提出的开放协议，用于不同 AI Agent 之间的互操作。",
    "docker": "Docker 是一个开源的容器化平台，可以让应用及其依赖打包成标准化单元。",
    "python": "Python 是一种解释型、高级、通用的编程语言，广泛应用于 AI 和 Web 开发。",
}


def generate_summary(topic: str) -> str:
    """优先调用 LLM 生成摘要，失败则回退到本地知识库。"""
    system_prompt = (
        "你是一名技术研究助手。用户会给你一个技术主题，"
        "请用 2-3 句话简明扼要地总结这个主题的核心概念和用途。"
        "回答用中文，控制在 150 字以内。"
        "直接输出最终答案，不要输出思考过程。"
    )

    llm_result = call_llm(system_prompt, f"请研究这个主题：{topic}")
    if llm_result:
        cleaned = llm_result.split("</think>")[-1].strip()
        return f"【研究摘要】\n主题：{topic}\n\n{cleaned}"

    topic_lower = topic.lower()
    base = KNOWLEDGE_BASE.get(topic_lower, f"关于 {topic} 的信息有限，建议进一步搜索。")
    return f"【研究摘要】\n主题：{topic}\n\n{base}\n\n（本地回退，未调用 LLM）"


def process_task(task: Task, store: InMemoryTaskStore):
    """研究 Agent 的核心处理逻辑。"""
    store.update_status(task, TaskState.WORKING, "正在研究...")

    user_text = ""
    for msg in task.history:
        if msg.role.value == "user":
            for part in msg.parts:
                if part.text:
                    user_text += part.text

    summary = generate_summary(user_text)
    store.add_artifact(task, "research-summary", summary, "text/markdown")
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


server = A2AJSONRPCServer(agent_card=agent_card, process_task=process_task)
app = server.build_app(title="Research Agent (A2A / JSON-RPC)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
