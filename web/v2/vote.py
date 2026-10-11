"""委员会独立投票：解析 / 聚合 / 匿名渲染纯函数（v1）。

匿名不变量：本模块不感知席位名与票的对应关系对外暴露——aggregate 返回的
ballots 已按 task.id 洗牌，调用方只落盘/展示该匿名序列。
"""

import json
import random
import re

from web.v2.models import Ballot, CommitteeVote, V2Task

REVIEW_VOTE_QUESTION = "是否认可当前讨论方向（可推进到建议整理阶段）？"

_VERDICTS = ("approve", "adjust", "reject")
_ANON_LABELS = ("评审 1", "评审 2", "评审 3", "评审 4")
_VERDICT_LABELS = {"approve": "赞成", "adjust": "调整", "reject": "反对", "abstain": "弃权"}


def build_vote_prompt(task: V2Task) -> str:
    """投票指令正文（不含身份行；身份行由 agents_client 注入）。"""
    constraints = "\n".join(
        f"- {'[已确认] ' if c.confirmed else ''}{c.text}" for c in task.constraints
    ) or "（尚无）"
    discussion = "\n".join(
        f"- {t.author}（{t.stage}）：{t.title}" for t in task.turns if t.kind == "statement"
    )
    return (
        f"{REVIEW_VOTE_QUESTION}\n\n"
        f"目标：{task.goal_text}\n\n"
        f"约束：\n{constraints}\n\n"
        f"近期讨论（发言标题）：\n{discussion}\n\n"
        "评判标准：与已确认约束的一致性、可行性、未被讨论的风险。\n"
        '只输出一个 JSON 对象，格式：{"verdict": "approve|adjust|reject", "confidence": 1到5的整数, "reason": "不超过60字的理由"}\n'
        "不要输出其他内容。"
    )


def parse_ballot(text: str) -> Ballot | None:
    """从模型输出中抽取选票 JSON；不可解析或 verdict 非法返回 None。"""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    candidates.extend(re.findall(r"\{[^{}]*\}", text, re.DOTALL))
    for raw in candidates:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if not isinstance(data, dict) or data.get("verdict") not in _VERDICTS:
            continue
        try:
            confidence = max(1, min(5, int(data.get("confidence", 3))))
        except Exception:
            confidence = 3
        reason = str(data.get("reason") or "")[:60].strip()
        return Ballot(verdict=data["verdict"], confidence=confidence, reason=reason)
    return None


def aggregate(task: V2Task, ballots_by_seat: dict[str, Ballot]) -> CommitteeVote:
    """聚合并按 task.id 洗牌（确定性）；abstain 不计入 tally。"""
    rng = random.Random(task.id)
    ballots = [ballots_by_seat[seat] for seat in sorted(ballots_by_seat)]
    rng.shuffle(ballots)
    tally = {v: 0 for v in _VERDICTS}
    quorum = 0
    for b in ballots:
        if b.verdict != "abstain":
            tally[b.verdict] += 1
            quorum += 1
    return CommitteeVote(tally=tally, split=_split_of(tally), ballots=ballots, quorum=quorum)


def _split_of(tally: dict[str, int]) -> str:
    counts = sorted(tally.values(), reverse=True)
    if counts[0] == 4:
        return "unanimous"
    if counts[0] >= 2:
        return "majority"
    return "split"


def render_summary(vote_result: CommitteeVote) -> str:
    """vote_summary turn 的 body：计票 + 匿名票（与前端展示一致）。"""
    lines = [f"委员会投票（{_VERDICT_LABELS['approve']} {vote_result.tally['approve']} / "
             f"{_VERDICT_LABELS['adjust']} {vote_result.tally['adjust']} / "
             f"{_VERDICT_LABELS['reject']} {vote_result.tally['reject']}，"
             f"{_SPLIT_LABELS[vote_result.split]}）", ""]
    for i, b in enumerate(vote_result.ballots):
        label = _ANON_LABELS[i % len(_ANON_LABELS)]
        if b.verdict == "abstain":
            lines.append(f"- {label}：弃权")
        else:
            lines.append(f"- {label}：{_VERDICT_LABELS[b.verdict]}（信心 {b.confidence}/5）—— {b.reason}")
    return "\n".join(lines)


_SPLIT_LABELS = {"unanimous": "全票一致", "majority": "多数意见", "split": "意见分裂"}
