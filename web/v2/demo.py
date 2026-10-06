"""V2 决策工作台的确定性演示脚本。

统一演示任务（goal_text == DEMO_GOAL）返回 Figma 逐字文案；
其他目标用参数化模板，正文嵌入任务目标与已确认约束，全程无时间戳/随机数。
"""

import os

from web.v2.models import (
    AcceptanceItem,
    ActionItem,
    EvidenceItem,
    OutcomeDoc,
    PathOption,
    Reason,
    SummaryGroups,
    V2Task,
)

DEMO_GOAL = "判断团队是否需要引入 A2A"

DEMO_CONSTRAINTS: list[str] = [
    "已有内部 MCP 工具接入",
    "首阶段优先私有化",
    "只验证一个跨团队协作场景",
]

DEMO_QUESTION = "首轮试点是否允许连接外部 Agent？"

DEMO_OPTIONS: list[dict] = [
    {
        "id": "o1",
        "label": "仅内部 Agent",
        "impact": "保持私有化边界",
        "recommended": True,
        "uncertain": False,
    },
    {
        "id": "o2",
        "label": "允许受控外部接入",
        "impact": "追加外部信任与授权评审",
        "recommended": False,
        "uncertain": False,
    },
    {
        "id": "o3",
        "label": "暂不确定",
        "impact": "先补齐判断所需信息",
        "recommended": False,
        "uncertain": True,
    },
]

SCRIPTS: dict[str, tuple[str, str]] = {
    "clarify_ada": (
        "先分清协议职责，不把能力发现当成权限体系",
        "先把职责分清楚：MCP 处理工具与数据接入，A2A 面向 Agent 间的发现与任务协作，"
        "两者定位不同。它不能直接替代权限体系：对方声明了某项能力，不代表团队已授予访问权，"
        "具体能力仍需结合团队实现核实，再决定试点范围。",
    ),
    "compare_turing": (
        "从一个跨团队任务交接开始试点",
        "建议先让研究 Agent 与评审 Agent 跨团队协作，只验证一个场景。"
        "保留现有 MCP 接入，隔离工具权限，让协作层不直接扩大工具访问范围，"
        "试点结论才有对照价值。",
    ),
    "review_linus": (
        "对方声明的 capability，不等于获得授权",
        "发现某项能力不能代表信任：对方声明的 capability，不等于获得授权。"
        "试点前要验证身份映射、工具授权与审计边界，还要测试取消任务及失败恢复。"
        "首轮若接入外部 Agent，信任与运维范围都会扩大。",
    ),
    "uncertain_turing": (
        "再看一步：两条路径的影响差",
        "两条路径的差异不在协议本身：仅内部接入可以立刻开始，但跨团队协作收益无法验证；"
        "受控外部接入能验证真实协作价值，却要先把身份映射、工具授权与审计边界补齐。"
        "当前仍不确定的是外部 Agent 的信任成本，以及试点出现异常时的恢复手段。",
    ),
    "uncertain_linus": (
        "信息缺口清单",
        "要降低判断风险，先补齐这些信息：候选外部 Agent 的身份与所属组织；"
        "它需要的工具权限清单与现有授权边界的差距；任务取消与失败恢复的真实案例；"
        "试点期间的审计与回滚方案。信息齐了，再决定是否扩大接入范围。",
    ),
    "revise_turing": (
        "按新边界修订：首轮仅内部接入的试点路径",
        "按你确认的边界修订：首轮仅接入内部 Agent，现有 MCP 工具接入保持不变。"
        "试点路径收窄为研究 Agent 与评审 Agent 的单场景协作，工具权限在内部隔离，"
        "不引入外部信任评审，验收通过后再评估是否接入外部 Agent。",
    ),
    "recommend_sage": (
        "整理权衡：建议内部小范围试点",
        "汇总共识与分歧：共识是保留现有 MCP 接入、首阶段优先私有化；"
        "分歧在外部接入的价值与风险。建议开展内部小范围试点，暂不全面引入，"
        "先验证一个跨团队协作场景。未解决问题与验收条件已列出，整理后提交团队审批。",
    ),
}

_TEMPLATES: dict[str, tuple[str, str]] = {
    "clarify_ada": (
        "先厘清「{goal}」的事实边界",
        "围绕「{goal}」，先区分已有能力与待验证假设。已确认约束：{constraints}。"
        "协议职责与现有实现是否适配仍需逐项核实，不把能力发现当成权限体系。",
    ),
    "compare_turing": (
        "从一个小场景开始验证「{goal}」",
        "针对「{goal}」，建议只选一个可观测的小场景做对照验证。已确认约束：{constraints}。"
        "保留现有接入，隔离工具权限，让新协作层不直接扩大工具访问范围。",
    ),
    "review_linus": (
        "声明的 capability，不等于获得授权",
        "围绕「{goal}」的试点开始前，先验证身份映射、工具授权与审计边界，"
        "并测试取消任务及失败恢复。已确认约束：{constraints}。"
        "发现某项能力不能代表信任，扩大接入范围前先把风险边界写清楚。",
    ),
    "uncertain_turing": (
        "再看一步：两条路径的影响差",
        "对「{goal}」而言，两条路径的差别不在协议本身：维持现状可立即开始，但收益无法验证；"
        "推进试点能验证价值，但要先补齐授权与异常恢复手段。已确认约束：{constraints}。"
        "当前仍不确定的是成本与风险的量化。",
    ),
    "uncertain_linus": (
        "信息缺口清单",
        "要降低「{goal}」的判断风险，先补齐：候选接入方的身份与权限清单；"
        "与现有授权边界的差距；任务取消与失败恢复案例；试点审计与回滚方案。"
        "已确认约束：{constraints}。信息齐了再做决定。",
    ),
    "revise_turing": (
        "按新边界修订「{goal}」的试点路径",
        "按已确认约束修订路径：{constraints}。试点范围收窄到单一场景，"
        "保留现有接入不变，权限在内部隔离，验收通过后再评估扩展。",
    ),
    "recommend_sage": (
        "整理权衡：建议围绕「{goal}」小范围试点",
        "汇总「{goal}」的共识与分歧，建议小范围试点、暂不全面引入。"
        "已确认约束：{constraints}。未解决问题与验收条件已列出，整理后提交团队审批。",
    ),
}

ACK_RECEIVED = "已接收 · 将在当前发言结束后处理"

_STOP_CONDITION = "停止条件：验收不通过则暂停扩展，仅保留内部试点结论。"


def demo_enabled() -> bool:
    return os.getenv("V2_DEMO") == "1" or not os.getenv("LLM_API_KEY")


def _confirmed_constraint_texts(task: V2Task) -> list[str]:
    return [c.text for c in task.constraints if c.confirmed]


def _constraint_clause(texts: list[str]) -> str:
    return "；".join(texts) if texts else "（尚无）"


def statement(key: str, task: V2Task) -> tuple[str, str, bool]:
    if task.goal_text == DEMO_GOAL:
        title, body = SCRIPTS[key]
        return title, body, False
    title_tpl, body_tpl = _TEMPLATES[key]
    clause = _constraint_clause(_confirmed_constraint_texts(task))
    return (
        title_tpl.format(goal=task.goal_text),
        body_tpl.format(goal=task.goal_text, constraints=clause),
        False,
    )


def _demo_outcome(task: V2Task) -> OutcomeDoc:
    confirmed = ["保留现有 MCP 接入", "首阶段优先私有化"]
    for text in _confirmed_constraint_texts(task):
        if text not in confirmed:
            confirmed.append(text)
    return OutcomeDoc(
        conclusion=(
            "建议开展内部小范围试点，暂不全面引入 A2A：先用一个研究与评审 Agent 的"
            "跨团队协作场景验证收益，保留现有 MCP 工具接入，不扩大工具授权范围，"
            "通过验收后再决定是否扩展。"
        ),
        summary_groups=SummaryGroups(
            confirmed=confirmed,
            disputed=["外部接入的价值与风险尚有分歧"],
            unverified=["协议能力与内部实现的适配尚未核实"],
        ),
        reasons=[
            Reason(
                title="先验证协作价值，而不是替换已有接入",
                body="用一个跨团队任务交接场景验证协作收益，保留现有 MCP 接入，不替换已有体系。",
                refs=[1, 3],
            ),
            Reason(
                title="把风险留在可控的内部边界",
                body="首轮仅接入内部 Agent，身份映射、工具授权与审计边界都在团队控制范围内，风险可验证、可回退。",
                refs=[2, 4, 5],
            ),
            Reason(
                title="用试点结果决定是否扩展",
                body="以验收条件衡量试点结果，通过后再决定是否扩展到外部接入，避免未经验证就扩大范围。",
                refs=[4, 6],
            ),
        ],
        path_comparison=[
            PathOption(
                name="保持现状",
                desc="不引入 A2A，沿用现有流程与权限边界",
                pros=["无需新增协议运维，现有权限边界不变"],
                cons=["跨团队任务交接仍由现有流程承担，协作收益无法验证"],
                fit="适合：尚未找到明确协作场景时",
                recommended=False,
            ),
            PathOption(
                name="内部试点",
                desc="首轮仅接入内部 Agent，用单场景验证协作价值",
                pros=["以小范围验证价值，控制信任与接入范围"],
                cons=["需要补齐身份映射、任务追踪和异常恢复验证"],
                fit="前提：团队审批与验收条件明确",
                recommended=True,
            ),
        ],
        evidence=[
            EvidenceItem(
                seq_ref=1,
                stage="clarify",
                author="研究员 Ada",
                quote="MCP 与 A2A 的职责不同；能力适配仍待验证。",
            ),
            EvidenceItem(
                seq_ref=3,
                stage="compare",
                author="方案设计师 Turing",
                quote="提出研究与评审 Agent 的单场景协作路径。",
            ),
            EvidenceItem(
                seq_ref=4,
                stage="review",
                author="挑战者 Linus",
                quote="能力声明不是授权，需验证信任与运维边界。",
            ),
            EvidenceItem(
                seq_ref=5,
                stage="review",
                author="你",
                quote="首轮仅内部 Agent，现有 MCP 接入不改动。",
            ),
            EvidenceItem(
                seq_ref=6,
                stage="recommend",
                author="决策助手 Sage",
                quote="整理内部试点建议与验收条件，提交团队审批。",
            ),
        ],
        open_questions=[
            "内部 Agent 身份如何映射到现有授权？",
            "取消任务与失败恢复能否覆盖真实异常？",
            "试点的运维成本是否值得持续投入？",
        ],
        actions=[
            ActionItem(
                title="确定一个跨团队协作场景",
                detail="选定研究 → 评审任务，记录现有流程作为比较基线。",
            ),
            ActionItem(
                title="搭建隔离的内部试点",
                detail="确认身份映射与授权边界；保留现有 MCP 接入。",
            ),
            ActionItem(
                title="执行验收并复盘采用建议",
                detail="记录任务交接与异常恢复结果，再判断是否扩展。",
            ),
        ],
        acceptance=[
            AcceptanceItem(
                title="任务交接可追踪",
                detail="每次任务交接都有发起、接收与结果记录，可回查。",
            ),
            AcceptanceItem(
                title="取消与失败恢复可控",
                detail="试点中触发取消与异常场景，恢复流程验证通过。",
            ),
            AcceptanceItem(
                title="工具授权不被绕过",
                detail="协作层未扩大工具访问范围，授权边界与现状一致。" + _STOP_CONDITION,
            ),
        ],
    )


_FALLBACK_CONCLUSION = "讨论已完成，建议草稿待整理"


def _sage_recommend_turn(task: V2Task):
    return next(
        (
            t
            for t in reversed(task.turns)
            if t.kind == "statement" and t.author == "sage" and t.stage == "recommend"
        ),
        None,
    )


def _derived_outcome(task: V2Task) -> OutcomeDoc:
    """真实任务成果：只从已落库的讨论 turns 组装，绝不编造样板内容（§2）。

    结论取 Sage 发言的真实标题与正文摘录；理由取最近的非 Sage 发言；
    方案对比/行动项/验收条件等留空，由团队在成果页补充。
    """
    sage = _sage_recommend_turn(task)
    if sage is not None and sage.title:
        conclusion = sage.title
        if sage.body:
            conclusion = f"{conclusion}\n{sage.body[:200]}"
    else:
        conclusion = _FALLBACK_CONCLUSION
    recent = [t for t in task.turns if t.kind == "statement" and t.author != "sage"]
    reasons = [Reason(title=t.title, body=t.body[:120], refs=[t.seq]) for t in recent[-3:]]
    evidence = [
        EvidenceItem(seq_ref=t.seq, stage=t.stage, author=t.author, quote=t.body[:60])
        for t in task.turns
        if t.kind in ("statement", "decision_record")
    ]
    return OutcomeDoc(
        conclusion=conclusion,
        summary_groups=SummaryGroups(
            confirmed=_confirmed_constraint_texts(task),
            disputed=[],
            unverified=[t.title for t in task.turns if t.verified and t.title],
        ),
        reasons=reasons,
        evidence=evidence,
    )


def build_outcome(task: V2Task) -> OutcomeDoc:
    if task.goal_text == DEMO_GOAL:
        return _demo_outcome(task)
    return _derived_outcome(task)
