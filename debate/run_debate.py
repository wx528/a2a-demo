"""
Debate CLI 编排器：正反方多轮对抗 + 裁判总结，全程走 A2A JSON-RPC。

用法：
    uv run python debate/run_debate.py "AI 会取代大多数工作吗" \
        --pro socrates --con hume --rounds 2 [--out transcript.md]
"""

import argparse
import asyncio
import os
import sys
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.a2a_client import A2AJSONRPCClient
from debate.personas import get_persona

DEFAULT_AGENT_URL = "http://localhost:8003"
RETRIES = 1


class DebateAborted(RuntimeError):
    """重试后仍失败而中止；携带已完成部分的转录（可能为空串）。"""

    def __init__(self, reason: str, transcript_so_far: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.transcript_so_far = transcript_so_far


def artifact_text(task: dict) -> str:
    artifacts = task.get("artifacts") or []
    if not artifacts:
        return ""
    for part in artifacts[0].get("parts", []):
        if part.get("text"):
            return part["text"]
    return ""


def build_turn_message(motion: str, persona: dict, stance: str, opponent_text: str) -> str:
    return (
        f"[辩题/MOTION] {motion}\n"
        f"[角色/PERSONA] {persona['name']}（风格：{persona['style']}）\n"
        f"[立场/STANCE] {stance}\n"
        f"[对手论点/OPPONENT_ARGUMENTS]\n{opponent_text or '（无）'}"
    )


async def send_with_retry(client, message: str) -> str:
    last_error = None
    for _ in range(RETRIES + 1):
        try:
            task = await client.send_message(message)
            text = artifact_text(task)
            if text:
                return text
            last_error = RuntimeError("empty argument from debate-agent")
        except Exception as e:
            last_error = e
    raise RuntimeError(f"debate-agent failed after retry: {last_error}")


def _render_transcript(motion, pro, con, judge, rounds, turns, verdict=None) -> str:
    """按最终转录的格式渲染；无任何已完成内容时返回空串。"""
    if not turns and verdict is None:
        return ""
    lines = [
        f"# 辩论：{motion}\n",
        f"- 正方：{pro['name']}",
        f"- 反方：{con['name']}",
        f"- 轮数：{rounds}\n",
    ]
    for i, (name, stance, text) in enumerate(turns, 1):
        lines.append(f"## 第 {i} 手 · {name}（{stance}）\n\n{text}\n")
    if verdict is not None:
        lines.append(f"## 裁判总结 · {judge['name']}\n\n{verdict}\n")
    return "\n".join(lines)


async def run_debate_async(motion, pro_id, con_id, rounds, agent_url) -> str:
    pro = get_persona(pro_id)
    con = get_persona(con_id)
    judge = get_persona("judge")
    client = A2AJSONRPCClient(agent_url)

    turns = []  # (persona_name, stance, argument_text)

    async def _send(message: str) -> str:
        try:
            return await send_with_retry(client, message)
        except RuntimeError as e:
            raise DebateAborted(
                str(e),
                _render_transcript(motion, pro, con, judge, rounds, turns),
            ) from e

    last_con = ""
    for r in range(1, rounds + 1):
        opponent_for_pro = last_con
        pro_text = await _send(
            build_turn_message(motion, pro, "正方", opponent_for_pro)
        )
        turns.append((pro["name"], "正方", pro_text))

        con_text = await _send(
            build_turn_message(motion, con, "反方", pro_text)
        )
        turns.append((con["name"], "反方", con_text))
        last_con = con_text

    both = "\n\n---\n\n".join(f"{n}（{s}）：\n{t}" for n, s, t in turns)
    verdict = await _send(
        (
            f"[辩题/MOTION] {motion}\n"
            f"[角色/PERSONA] {judge['name']}（风格：{judge['style']}）\n"
            f"[立场/STANCE] 裁判\n"
            f"[对手论点/OPPONENT_ARGUMENTS]\n{both}"
        ),
    )

    return _render_transcript(motion, pro, con, judge, rounds, turns, verdict)


def run_debate(motion, pro_id, con_id, rounds, agent_url) -> str:
    return asyncio.run(
        run_debate_async(motion, pro_id, con_id, rounds, agent_url)
    )


def _emit_transcript(transcript: str, out_path: Optional[str]) -> None:
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(transcript)
        print(f"transcript written to {out_path}", file=sys.stderr)
    else:
        print(transcript)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="A2A persona debate runner")
    parser.add_argument("motion", help="辩题")
    parser.add_argument("--pro", default="socrates", help="正方人格 id（默认 socrates）")
    parser.add_argument("--con", default="hume", help="反方人格 id（默认 hume）")
    parser.add_argument("--rounds", type=int, default=2, help="辩论轮数（默认 2）")
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL, help="debate-agent 地址")
    parser.add_argument("--out", default=None, help="转录输出到文件（默认打印 stdout）")
    args = parser.parse_args(argv)

    if args.rounds < 1:
        parser.error("--rounds must be >= 1")
        return 2

    try:
        transcript = run_debate(args.motion, args.pro, args.con, args.rounds, args.agent_url)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        partial = getattr(e, "transcript_so_far", "")
        if partial:
            _emit_transcript(partial, args.out)
        print(f"error: {e}", file=sys.stderr)
        return 1

    _emit_transcript(transcript, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
