"""V2 角色 Agent 客户端：真实 LLM 发言后端（A2A JSON-RPC 流式调用）。

SpeakerBackend 的真实实现：按角色解析 Agent 地址，用结构化 prompt 调
stream_deltas，增量过滤 <think>/[PHASE] 后经 broadcaster 转发 turn_delta 事件；
异常时 1s 后重试一次，仍失败抛 AgentCallError（由编排器标记任务失败）。
"""

import asyncio
import os

from shared.a2a_client import A2AJSONRPCClient
from web.v2.models import V2Task
from web.v2.orchestrator import AgentCallError
from web.v2.util import ThinkFilter, _PHASE_LINE, _phase_or_none

ROLE_AGENTS: dict[str, str] = {
    "ada": "http://localhost:8011",
    "turing": "http://localhost:8012",
    "linus": "http://localhost:8013",
    "sage": "http://localhost:8014",
}

ROLE_PERSONAS: dict[str, str] = {
    "ada": "研究员 Ada：核实事实与不确定性",
    "turing": "方案设计师 Turing：提出可执行方案",
    "linus": "挑战者 Linus：检查风险与隐含假设",
    "sage": "决策助手 Sage：整理权衡与建议",
}

KEY_INSTRUCTIONS: dict[str, str] = {
    "clarify_ada": "澄清协作场景与约束，指出尚未核实的事实",
    "compare_turing": "提出最小可行的试点路径并说明取舍",
    "review_linus": "检查风险与隐含假设，指出信任与运维边界",
    "uncertain_turing": "继续比较两条路径的影响差异",
    "uncertain_linus": "列出补齐判断所需的信息缺口",
    "revise_turing": "根据用户刚确认的约束修订试点路径",
    "recommend_sage": "汇总共识与分歧，形成建议与验收条件，不代替团队决定",
}

_GENERIC_INSTRUCTION = "就当前讨论阶段给出你的专业发言"

_UNVERIFIED_MARKER = "# UNVERIFIED"

_RECENT_TURN_KINDS = ("statement", "user_note", "decision_record")
_RECENT_TURNS = 6
_TITLE_MAX = 40
_BODY_CLIP = 200


def reload_urls() -> None:
    """按 env ROLE_AGENT_URLS（格式 ada=http://..,turing=http://..）覆盖默认地址。"""
    raw = os.getenv("ROLE_AGENT_URLS", "")
    for pair in raw.split(","):
        name, sep, url = pair.strip().partition("=")
        name, url = name.strip(), url.strip()
        if sep and name in ROLE_AGENTS and url:
            ROLE_AGENTS[name] = url


def _recent_turns(task: V2Task) -> list:
    return [t for t in task.turns if t.kind in _RECENT_TURN_KINDS][-_RECENT_TURNS:]


def build_turn_prompt(task: V2Task, author: str, key: str) -> str:
    lines = [
        f"[目标] {task.goal_text}",
        f"[期望成果] {task.expected_outcome}",
        "[约束]",
    ]
    for c in task.constraints:
        mark = "✓" if c.confirmed else "·"
        lines.append(f"{mark} {c.text}")
    lines.append("[近期讨论]")
    for t in _recent_turns(task):
        lines.append(f"#{t.seq} {t.author}: {t.title} — {t.body[:_BODY_CLIP]}")
    lines.append("[你的任务]")
    lines.append(f"你是{ROLE_PERSONAS[author]}。{KEY_INSTRUCTIONS.get(key, _GENERIC_INSTRUCTION)}")
    return "\n".join(lines)


class AgentSpeakerBackend:
    """调用真实角色 Agent 的发言后端；编排器据返回值建 Turn。"""

    def __init__(self, broadcaster):
        self.broadcaster = broadcaster

    async def speak(self, task: V2Task, author: str, key: str) -> tuple[str, str, bool]:
        try:
            url = ROLE_AGENTS[author]
        except KeyError as exc:
            raise AgentCallError(f"未知角色，无对应 Agent 地址：{author}") from exc
        prompt = build_turn_prompt(task, author, key)
        try:
            text = await self._stream_text(task, author, url, prompt)
            self._require_valid_text(text, author)
        except Exception:
            await asyncio.sleep(1)
            try:
                text = await self._stream_text(task, author, url, prompt)
                self._require_valid_text(text, author)
            except Exception as retry_exc:
                raise AgentCallError(f"角色 {author} 调用失败：{retry_exc}") from retry_exc
        return self._split_turn_text(text)

    def _require_valid_text(self, text: str, author: str) -> None:
        """空响应或角色 Agent 的 fallback 占位文案一律视为失败（§3.1：绝不静默用占位发言）。"""
        if not text.strip() or "暂未能生成发言" in text:
            raise AgentCallError(f"角色 {author} 未产出有效发言")

    async def _stream_text(self, task: V2Task, author: str, url: str, prompt: str) -> str:
        client = A2AJSONRPCClient(url)
        think = ThinkFilter()
        parts: list[str] = []
        async for delta in client.stream_deltas(prompt):
            if not delta:
                continue
            if _phase_or_none(delta) is not None:
                continue
            piece = think.feed(delta)
            if not piece:
                continue
            parts.append(piece)
            self._publish_delta(task, author, piece)
        tail = think.final_text()
        if tail:
            parts.append(tail)
            self._publish_delta(task, author, tail)
        return _PHASE_LINE.sub("", "".join(parts)).strip()

    def _publish_delta(self, task: V2Task, author: str, piece: str) -> None:
        self.broadcaster.publish(task.id, "turn_delta", {"author": author, "delta": piece})

    def _split_turn_text(self, text: str) -> tuple[str, str, bool]:
        verified = _UNVERIFIED_MARKER in text
        text = text.replace(_UNVERIFIED_MARKER, "").strip()
        lines = text.split("\n")
        first = lines[0].strip()
        if 0 < len(first) <= _TITLE_MAX:
            return first, "\n".join(lines[1:]).strip(), verified
        return "", text, verified
