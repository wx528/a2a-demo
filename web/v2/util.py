"""V1/V2 共用的流式文本工具：think 推理前缀过滤、[PHASE] 标记解析与 SSE 事件格式化。"""

import json
import re
from typing import Optional

_PHASE_LINE = re.compile(r"\[PHASE\][^\n]*\n?")


def sse_event(event: str, data: dict) -> str:
    """格式化一条 SSE 事件（V1 会议流与 V2 任务流共用）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _phase_or_none(delta: str) -> Optional[str]:
    """[PHASE] 标记行返回文案（供 agent_phase 事件），其余返回 None。"""
    if delta.startswith("[PHASE]"):
        return delta[len("[PHASE]"):].strip()
    return None


class ThinkFilter:
    """累积增量并过滤 <think>…</think> 推理前缀：见到闭合标签后才放行后续内容。"""

    def __init__(self):
        self.buf = ""
        self.open_ended = False

    def feed(self, delta: str) -> str:
        if self.open_ended:
            return delta
        self.buf += delta
        end = self.buf.find("</think>")
        if end != -1:
            self.open_ended = True
            self.buf = ""
            return delta[end + len("</think>"):]
        # 保留可能被截断的标签尾巴，避免误发半个 "<thi"
        keep = 8
        if len(self.buf) > keep:
            pending, emit = self.buf[-keep:], self.buf[:-keep]
            self.buf = pending
            return emit
        return ""

    def final_text(self) -> str:
        if self.open_ended:
            return ""
        text = self.buf.split("</think>")[-1]
        self.buf = ""
        return text
