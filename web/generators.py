"""
LLM 生成器：候选议题与辩论双方开篇立论预览。
web 进程内直接调用 shared.llm_client（.env 已由 main 加载），同步调用统一用 asyncio.to_thread 包装。
"""

import asyncio
import json
from typing import List, Tuple

from shared.llm_client import call_llm


def _extract_json_array(text: str) -> List[str]:
    """从 LLM 输出中稳健地提取字符串数组：优先解析 [..]，退化按行切分。"""
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            items = [str(t).strip() for t in data if str(t).strip()]
            if items:
                return items
        except json.JSONDecodeError:
            pass
    lines = (ln.strip(" \t-*0123456789.、") for ln in text.splitlines())
    return [ln for ln in lines if ln]


async def suggest_topics(count: int = 3, seed: str = "") -> List[str]:
    if seed.strip():
        user_prompt = (
            f"用户输入的关键词/主题是：「{seed.strip()}」。\n"
            f"请围绕这个关键词生成 {count} 个中文议题，"
            "每条不超过 20 字，有正反讨论空间或值得多方探讨。"
        )
    else:
        user_prompt = (
            f"请生成 {count} 个适合 AI Agent 辩论或圆桌讨论的中文议题，"
            "主题领域多样（科技、社会、商业、伦理等），每条不超过 20 字，有正反讨论空间。"
        )

    def _run() -> List[str]:
        result = call_llm(
            "你是一场 AI Agent 多人会议的主持人，负责出题。只输出 JSON 字符串数组，不要输出任何其它内容。",
            user_prompt,
            max_tokens=500,
        )
        if not result:
            raise ValueError("LLM 返回为空")
        topics = _extract_json_array(result)
        if not topics:
            raise ValueError("无法解析议题列表")
        return topics[:count]

    return await asyncio.to_thread(_run)


async def preview_viewpoints(topic: str, pro_id: str, con_id: str) -> Tuple[str, str]:
    from debate.personas import PERSONAS

    def _one(pid: str, stance: str) -> str:
        persona = PERSONAS[pid]
        system = (
            f"你是{stance}辩手。人格设定：{persona['name']}——{persona['style']}。"
            "直接输出论点正文，不要输出思考过程或任何前后缀。"
        )
        user = f"辩题：{topic}\n请给出你方开篇立论，120 字以内。"
        for _ in range(2):  # LLM 偶发抖动重试一次
            result = call_llm(system, user, max_tokens=350)
            if result:
                return result.split("</think>")[-1].strip()
        return "（生成失败，请重试）"

    async def _side(pid: str, stance: str) -> str:
        return await asyncio.to_thread(_one, pid, stance)

    pro, con = await asyncio.gather(_side(pro_id, "正方"), _side(con_id, "反方"))
    return pro, con
