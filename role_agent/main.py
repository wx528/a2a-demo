"""
Role Agent - V2 圆桌讨论角色 Agent（一份代码，四个 compose 实例）
通过 env ROLE 选择角色：ada（研究员）| turing（方案设计师）| linus（挑战者）| sage（决策助手）
"""

import os
import sys
from typing import Iterator, NamedTuple

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


AGENT_PORT = int(os.getenv("PORT", 8011))
AGENT_HOST = os.getenv("HOST", "localhost")
BIND_HOST = os.getenv("BIND_HOST", "127.0.0.1")  # 监听接口：本地默认只听回环，容器经 BIND_HOST=0.0.0.0 显式放开
# 可通过 AGENT_URL 覆盖 Agent Card 中对外暴露的 URL（例如公网地址、Docker 外部地址）
AGENT_URL = os.getenv("AGENT_URL", f"http://{AGENT_HOST}:{AGENT_PORT}")

# 无 LLM 时的诚实回退模板（fallback 仅在全程无可见输出时产出）
FALLBACK_TEMPLATE = "[{zh_name}暂未能生成发言，请稍后重试]"


class RoleMeta(NamedTuple):
    zh_name: str
    en_name: str
    emoji: str
    duty: str


ROLE_META = {
    "ada": RoleMeta(
        zh_name="研究员",
        en_name="Ada",
        emoji="🧬",
        duty="核实决策相关事实与不确定性，区分 MCP 与 A2A 的信息来源，标记未核实结论",
    ),
    "turing": RoleMeta(
        zh_name="方案设计师",
        en_name="Turing",
        emoji="🧠",
        duty="提出可执行的候选方案，设计最小试点路径",
    ),
    "linus": RoleMeta(
        zh_name="挑战者",
        en_name="Linus",
        emoji="⚡",
        duty="检查方案的风险与隐含假设：身份、授权、失败恢复、审计边界",
    ),
    "sage": RoleMeta(
        zh_name="决策助手",
        en_name="Sage",
        emoji="⚖️",
        duty="整理权衡与建议，明确共识、分歧与待验证事项，不代替团队决定",
    ),
}

OUTPUT_FORMAT_RULES = (
    "输出要求：先输出一行观点标题（不超过 20 字，不带句号），空一行后输出正文；"
    "正文用简体中文；不得虚构引用来源、负责人或日期。"
)
ADA_EXTRA_RULE = "对任何未经核实的结论，在正文末尾单独一行输出 # UNVERIFIED。"

ROLE_PERSONA_PROMPTS = {
    "ada": (
        "你是圆桌讨论中的研究员 Ada。职责：核实事实与不确定性；"
        "区分 MCP（工具直连）与 A2A（代理间协作）的信息来源；"
        "明确标记尚未核实的能力与结论。\n" + OUTPUT_FORMAT_RULES + ADA_EXTRA_RULE
    ),
    "turing": (
        "你是圆桌讨论中的方案设计师 Turing。职责：针对议题提出可执行的候选方案，"
        "并给出最小试点路径。\n" + OUTPUT_FORMAT_RULES
    ),
    "linus": (
        "你是圆桌讨论中的挑战者 Linus。职责：检查当前方案的风险与隐含假设，"
        "重点关注身份、授权、失败恢复与审计边界。\n" + OUTPUT_FORMAT_RULES
    ),
    "sage": (
        "你是圆桌讨论中的决策助手 Sage。职责：整理各角色的权衡与建议，"
        "明确共识、分歧与待验证事项；你只提供建议，不代替团队做决定。\n" + OUTPUT_FORMAT_RULES
    ),
}

# 各角色在其阶段职责上对外声明的一项技能（clarify / compare / review / recommend）
ROLE_SKILLS = {
    "ada": AgentSkill(
        id="clarify",
        name="事实澄清",
        description="澄清决策议题，拆解需要核实的事实与不确定性，区分 MCP 与 A2A 的信息来源",
        tags=["clarify", "research"],
        examples=["厘清这个选型争议的事实基础"],
    ),
    "turing": AgentSkill(
        id="compare",
        name="方案对比",
        description="提出可执行的候选方案，并设计最小试点路径",
        tags=["compare", "plan"],
        examples=["对比自建与采购两个方案"],
    ),
    "linus": AgentSkill(
        id="review",
        name="风险审视",
        description="检查方案的风险与隐含假设：身份、授权、失败恢复、审计边界",
        tags=["review", "risk"],
        examples=["评估这个方案的风险"],
    ),
    "sage": AgentSkill(
        id="recommend",
        name="权衡建议",
        description="整理各方权衡，明确共识、分歧与待验证项，不代替团队决定",
        tags=["recommend", "decision"],
        examples=["给出最终决策建议"],
    ),
}

# 启动即校验 ROLE，配置错误快速失败
role = os.getenv("ROLE", "ada").strip().lower()
if role not in ROLE_META:
    raise ValueError(f"未知 ROLE: {role!r}，可选值：ada | turing | linus | sage")
meta = ROLE_META[role]


def _search_context(query: str) -> str:
    """Ada 专属：检索补充资料；任何失败都不阻塞发言。"""
    try:
        sources = web_search(query[:80], max_results=4)
        if not sources:
            return ""
        lines = [
            f"[资料{i}] {s.get('title', '')}\n摘要: {s.get('snippet', '')}"
            for i, s in enumerate(sources, 1)
        ]
        return "检索资料：\n" + "\n\n".join(lines)
    except Exception:
        return ""  # 检索失败不阻塞发言


def stream_response(task: Task, store: InMemoryTaskStore) -> Iterator[str]:
    """流式发言：[PHASE]/<think> 标记原样输出，由调用方（web 侧）统一过滤。"""
    prompt = collect_user_text(task)
    search_context = _search_context(prompt) if role == "ada" else ""
    yield from agentic_stream(
        system=ROLE_PERSONA_PROMPTS[role],
        user=prompt,
        search_context=search_context,
        max_tokens=8000,
        fallback=FALLBACK_TEMPLATE.format(zh_name=meta.zh_name),
    )


def process_task(task: Task, store: InMemoryTaskStore):
    """非流式发言：同一人格，一次成稿。"""
    store.update_status(task, TaskState.WORKING, "正在思考...")

    response = call_llm(ROLE_PERSONA_PROMPTS[role], collect_user_text(task), max_tokens=8000)
    if not response:
        response = FALLBACK_TEMPLATE.format(zh_name=meta.zh_name)
    response = response.split("</think>")[-1].strip()
    if not response:
        response = FALLBACK_TEMPLATE.format(zh_name=meta.zh_name)

    store.add_artifact(task, "response", response, "text/markdown")
    store.update_status(task, TaskState.COMPLETED, "发言完成")


agent_card = AgentCard(
    name=f"{meta.zh_name} · {meta.en_name}",
    description=meta.duty,
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
    skills=[ROLE_SKILLS[role]],
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
app = server.build_app(title=f"Role Agent - {meta.en_name} (A2A / JSON-RPC)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=BIND_HOST, port=AGENT_PORT)
