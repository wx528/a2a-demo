"""
会议室轮次调度器（纯函数）。

序列 + 游标（turn_state.seq_index）驱动三种模式；游标推进由执行器持久化。
pipeline 耗尽后若最后一条非系统消息来自用户，则重置游标并切换主题
（对应旧 /run 的重新触发语义）；topic_override 在整轮重启流程内持续生效。
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PIPELINE_STEPS = ["research", "writing", "review", "code", "summary"]
ROUNDTABLE_AGENTS = ["research", "writing", "review", "code", "summary"]


def build_sequence(mode: str, max_rounds: int) -> List[Tuple[str, str]]:
    if mode == "roundtable":
        seq = [("agent", "moderator")]
        for _ in range(max(1, max_rounds)):
            seq += [("agent", k) for k in ROUNDTABLE_AGENTS]
        seq += [("fallback", "research"), ("agent", "moderator")]
        return seq
    if mode == "debate":
        seq = []
        for _ in range(max(1, max_rounds)):
            seq += [("debate", "pro"), ("debate", "con")]
        return seq + [("judge", "judge")]
    return [("agent", k) for k in PIPELINE_STEPS]


def _last_non_system(meeting) -> Optional[object]:
    for m in reversed(meeting.messages):
        if m.type != "system":
            return m
    return None


def next_turn(meeting) -> Tuple[Optional[Dict], Dict]:
    """返回 (spec|None, 新 turn_state)。spec = {"kind","key","index"}。不修改 meeting。"""
    seq = build_sequence(meeting.mode, meeting.max_rounds)
    state: Dict = dict(meeting.turn_state or {})
    index = int(state.get("seq_index", 0))

    if index >= len(seq):
        last = _last_non_system(meeting)
        if (
            meeting.mode == "pipeline"
            and last is not None
            and last.participant_id == "user"
        ):
            state = {"seq_index": 0, "topic_override": last.content}
            index = 0
        else:
            return None, state

    kind, key = seq[index]
    return {"kind": kind, "key": key, "index": index}, state


def next_turn_with_index(meeting, index: int) -> Tuple[Optional[Dict], Dict]:
    """跳位推进（fallback 被跳过时执行器用）。"""
    state: Dict = dict(meeting.turn_state or {})
    seq = build_sequence(meeting.mode, meeting.max_rounds)
    if index >= len(seq):
        return None, state
    state["seq_index"] = index
    kind, key = seq[index]
    return {"kind": kind, "key": key, "index": index}, state


def skip_fallback(seq, index: int, meeting) -> bool:
    """roundtable 保底步：开场之后已有讨论 agent 发过言则跳过。"""
    if seq[index] != ("fallback", "research"):
        return False
    return any(m.participant_id in ROUNDTABLE_AGENTS for m in meeting.messages)


def advance(meeting, steps: int = 1) -> Dict:
    """执行器调用：游标前进步数（fallback 被跳过时为 2）。topic_override 保留至整轮结束。"""
    state: Dict = dict(meeting.turn_state or {})
    state["seq_index"] = int(state.get("seq_index", 0)) + steps
    return state
