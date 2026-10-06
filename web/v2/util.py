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
    """过滤一条流中任意数量的 <think>…</think> 块（可重复、可跨增量截断标签）。

    GLM 等推理模型会先输出自己的思考块，agent_loop 又会把草稿/自审包进
    额外的 think 块，因此不能只吞到第一个闭合标签就放行后续内容。
    """

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self):
        self.in_think = False
        self.tail = ""  # 可能是被截断的标签前缀，留待下个增量裁决

    def feed(self, delta: str) -> str:
        data = self.tail + delta
        self.tail = ""
        out: list[str] = []
        while data:
            if self.in_think:
                idx = data.find(self._CLOSE)
                if idx == -1:
                    keep = len(self._CLOSE) - 1
                    self.tail = data[-keep:] if len(data) > keep else data
                    data = ""
                else:
                    data = data[idx + len(self._CLOSE):]
                    self.in_think = False
            else:
                idx = data.find(self._OPEN)
                if idx == -1:
                    keep = len(self._OPEN) - 1
                    cut = len(data) - keep
                    if cut > 0:
                        out.append(data[:cut])
                        self.tail = data[cut:]
                    else:
                        self.tail = data
                    data = ""
                else:
                    out.append(data[:idx])
                    data = data[idx + len(self._OPEN):]
                    self.in_think = True
        return "".join(out)

    def final_text(self) -> str:
        rest, self.tail = self.tail, ""
        if self.in_think:
            return ""
        return rest
