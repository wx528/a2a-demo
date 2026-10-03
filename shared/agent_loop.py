"""
Agent 内循环：起草 → 自我审视 → 修订定稿，流式输出。

中间阶段以 <think>…</think> 包裹（消费端过滤器自动隐藏），
阶段切换以整行 "[PHASE] 标签" 一次性产出（消费端拦截为状态事件）。
任何中间阶段失败自动降级：跳过该阶段，最终阶段仍照常执行。
"""

from typing import Iterator, List

from shared.llm_client import call_llm, call_llm_stream

CRITIQUE_SYSTEM = (
    "你是严格的编辑。基于上下文与草稿，指出 3 条最影响质量的改进点，"
    "每条一行、直给结论，不要客套，不要输出思考过程。"
)


def agentic_stream(
    system: str,
    user: str,
    search_context: str = "",
    critique: bool = True,
    max_tokens: int = 2000,
    fallback: str = "",
) -> Iterator[str]:
    """流式产出：[PHASE] 标记 + <think> 隐藏中间产物 + 最终定稿增量。

    fallback：当全程没有产出任何可见内容时（如 LLM 不可用），额外产出该文本。
    """
    visible_chars = 0
    draft_ctx = f"{search_context}\n\n{user}" if search_context else user

    yield "[PHASE] 整理思路并起草"
    draft_parts: List[str] = []
    draft_stream = call_llm_stream(
        f"{system}\n\n（当前为内部草稿阶段，尽情展开，之后会有修订机会。）",
        draft_ctx,
        max_tokens=max_tokens,
    )
    yield "<think>\n"
    for delta in draft_stream or []:
        if delta:
            draft_parts.append(delta)
            yield delta
    yield "\n</think>\n"
    draft_text = "".join(draft_parts).split("</think>")[-1].strip()

    revision_user = user
    if critique and draft_text:
        yield "[PHASE] 自我审视"
        try:
            critique_text = call_llm(
                CRITIQUE_SYSTEM,
                (
                    f"{search_context}\n\n"
                    f"【原始要求】\n{user}\n\n【草稿】\n{draft_text}"
                ),
                max_tokens=400,
            )
            if critique_text:
                critique_text = critique_text.split("</think>")[-1].strip()
                yield f"<think>\n{critique_text}\n</think>\n"
                revision_user = (
                    f"{user}\n\n"
                    f"【你的草稿】\n{draft_text}\n\n"
                    f"【编辑意见】\n{critique_text}\n\n"
                    "请据此输出最终版发言：修正问题、保留亮点、直接输出正文。"
                )
        except Exception:
            pass  # 自审失败则按原要求直出

    yield "[PHASE] 输出最终发言"
    for delta in call_llm_stream(system, revision_user, max_tokens=max_tokens) or []:
        if delta:
            visible_chars += len(delta)
            yield delta

    if visible_chars == 0 and fallback:
        yield fallback
