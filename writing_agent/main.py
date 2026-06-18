"""
Writing Agent - A2A 合规示例（JSON-RPC 2.0 绑定）
能力：基于研究摘要，生成一篇格式化文章
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


AGENT_PORT = int(os.getenv("PORT", 8002))
AGENT_HOST = os.getenv("HOST", "localhost")
AGENT_URL = os.getenv("AGENT_URL", f"http://{AGENT_HOST}:{AGENT_PORT}")


def generate_article(research_summary: str) -> str:
    """优先调用 LLM 生成文章，失败则回退到模板。"""
    lines = research_summary.split("\n")
    topic = "该主题"
    for line in lines:
        if line.startswith("主题："):
            topic = line.replace("主题：", "").strip()
            break

    system_prompt = (
        "你是一名技术博客作者。请根据提供的研究摘要，"
        "写一篇结构清晰的 Markdown 格式入门文章。"
        "文章包含：引言、核心概念、应用场景、总结四个部分。"
        "回答用中文。"
        "直接输出文章正文，不要输出思考过程。"
    )

    llm_result = call_llm(
        system_prompt,
        f"请基于以下摘要写一篇文章：\n\n{research_summary}",
        max_tokens=4000,
    )
    if llm_result:
        cleaned = llm_result.split("</think>")[-1].strip()
        return cleaned

    article = f"""# {topic} 入门指南

## 引言

{topic} 是当前技术领域的重要话题。本文将从基础概念出发，帮助读者快速理解其核心思想。

## 核心概念

{research_summary}

## 应用场景

- 企业级系统构建
- 自动化流程编排
- 提升开发运维效率

## 总结

掌握 {topic} 对于现代软件工程师来说越来越重要，建议从官方文档和实践项目入手。

（本地回退，未调用 LLM）
"""
    return article


def process_task(task: Task, store: InMemoryTaskStore):
    """写作 Agent 的核心处理逻辑。"""
    store.update_status(task, TaskState.WORKING, "正在写作...")

    user_text = ""
    for msg in task.history:
        if msg.role.value == "user":
            for part in msg.parts:
                if part.text:
                    user_text += part.text

    article = generate_article(user_text)
    store.add_artifact(task, "article", article, "text/markdown")
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


server = A2AJSONRPCServer(agent_card=agent_card, process_task=process_task)
app = server.build_app(title="Writing Agent (A2A / JSON-RPC)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
