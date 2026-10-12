"""决策质量评测：单 LLM 直答 vs 委员会流程（4 席 + 投票 + 门）LLM-as-judge 对比。

用法（需 LLM_API_KEY + 可达的 4 个角色 agent，默认 127.0.0.1:8011-8014）：

    uv run python evals/quality/decision_eval.py --limit 3

- 基线：同一模型单次直答（system = 决策顾问）
- 处理组：in-process 驱动 V2 全流程（clarify→compare→review→投票→门自动采纳→修订→综合）
- 裁判：Judge（JUDGE_* 回退 LLM_*），盲评（A/B 随机命名），四维 1-10 + 胜负
- 报告：evals/reports/decision-<ts>.json / .md（目录 gitignored）
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.env import load_env
from shared.llm_client import call_llm

from evals.quality.judge import Judge

QUESTIONS = [
    {"id": "q01", "goal": "5 人团队要不要引入每日站会", "expected_outcome": "一份会议制度建议", "constraints": ["成员分布在两个时区", "现有周会保留"]},
    {"id": "q02", "goal": "内部工具要不要从自建迁移到采购 SaaS", "expected_outcome": "迁移或保留的取舍建议", "constraints": ["年度预算上限 20 万", "数据不能出私有网络"]},
    {"id": "q03", "goal": "新功能要不要做免费试用而不是 14 天付费墙", "expected_outcome": "定价与试用策略建议", "constraints": ["销售团队 3 人", "当前月流失率 8%"]},
    {"id": "q04", "goal": "要不要把技术文档从 Wiki 迁到仓库内 Markdown", "expected_outcome": "文档治理建议", "constraints": ["非技术同事也要能编辑", "不能中断进行中的项目"]},
    {"id": "q05", "goal": "要不要为核心服务增加多区域部署", "expected_outcome": "部署架构建议", "constraints": ["当前用户 90% 在单一区域", "运维团队 2 人"]},
    {"id": "q06", "goal": "实习转正名额要不要从 2 个扩到 4 个", "expected_outcome": "名额与培养计划建议", "constraints": ["mentor 精力有限", "明年 headcount 未定"]},
    {"id": "q07", "goal": "老服务要不要在重构前先补自动化测试", "expected_outcome": "重构前置工作排序建议", "constraints": ["重构窗口只有 6 周", "测试基建从零开始"]},
    {"id": "q08", "goal": "要不要给开源项目加行为准则与治理文档", "expected_outcome": "社区治理建议", "constraints": ["当前贡献者 10 人以内", "维护者只有 1 人"]},
    {"id": "q09", "goal": "数据看板要不要统一到单一 BI 工具", "expected_outcome": "工具整合建议", "constraints": ["现有三套工具各有忠实用户", "采购流程周期 2 个月"]},
    {"id": "q10", "goal": "要不要在客户端内嵌自研更新通道", "expected_outcome": "更新机制取舍建议", "constraints": ["客户端月活 5 万", "安全合规要求可审计"]},
]

_BASELINE_SYSTEM = "你是一位务实的决策顾问。直接给出结构化建议：结论、理由、风险、下一步。不超过 400 字。"


def _baseline_answer(q: dict) -> Optional[str]:
    """基线：单 LLM 直答（与处理组同一模型配置）。"""
    user = (
        f"要做的判断：{q['goal']}\n"
        f"期望成果：{q['expected_outcome']}\n"
        f"约束：\n" + "\n".join(f"- {c}" for c in q["constraints"])
    )
    return call_llm(_BASELINE_SYSTEM, user, max_tokens=2000)


def _committee_answer(q: dict, workdir: Path) -> tuple[Optional[str], Optional[dict], Optional[str]]:
    """处理组：in-process 驱动 V2 全流程，返回 (conclusion, committee_vote_dict)。

    用生产同一后端接缝（DemoOrRealBackend）：V2_DEMO=1 时零真实调用（离线测试可用），
    否则打真实角色 agent（ROLE_AGENT_URLS，默认 127.0.0.1:8011-8014）。
    """
    import os
    import tempfile

    from web.v2.models import V2Task
    from web.v2.orchestrator import NullBroadcaster, Orchestrator
    from web.v2.routes import DemoOrRealBackend
    from web.v2.store import V2Store

    with tempfile.TemporaryDirectory(dir=str(workdir)) as td:
        store = V2Store(str(Path(td) / "v2.db"))
        store.init()
        task = V2Task(
            id=q["id"],
            goal_type="decision",
            goal_text=q["goal"],
            expected_outcome=q["expected_outcome"],
            constraints=[{"text": c} for c in q["constraints"]],
            demo=os.getenv("V2_DEMO") == "1",  # 与 routes 建任务同语义；离线测试用
            created_at=time.time(),
            updated_at=time.time(),
        )
        store.save_task(task)
        orch = Orchestrator(store, DemoOrRealBackend(broadcaster=NullBroadcaster()), _NullBroadcaster())

        async def _drive():
            await asyncio.wait_for(orch.run_task(task.id), timeout=900)
            t = store.get_task(task.id)
            if t.status != "waiting_confirmation":
                return t
            d = t.decisions[0]
            await asyncio.wait_for(orch.submit_decision(task.id, d.id, "o1"), timeout=900)
            return store.get_task(task.id)

        t = asyncio.run(_drive())
        if t.status != "completed" or t.outcome is None:
            return None, None, t.error
        vote = t.committee_vote.model_dump() if t.committee_vote else None
        return t.outcome.conclusion, vote, None


class _NullBroadcaster:
    def publish(self, task_id: str, event: str, data: dict) -> None:
        pass


_JUDGE_SYSTEM = (
    "你是盲评裁判。给你同一决策问题的两个独立建议（方案A/方案B，顺序随机）。"
    "按四个维度各打 1-10 分：constraint_adherence（对给定约束的遵守）、"
    "risk_coverage（风险识别）、executability（可执行性/下一步清晰度）、"
    "coherence（论证自洽）。只输出 JSON："
    '{"constraint_adherence_a": n, "constraint_adherence_b": n, '
    '"risk_coverage_a": n, "risk_coverage_b": n, '
    '"executability_a": n, "executability_b": n, '
    '"coherence_a": n, "coherence_b": n, '
    '"winner": "A|B|tie", "reason": "不超过80字"}'
)

_CRITERIA = ("constraint_adherence", "risk_coverage", "executability", "coherence")


def _judge_compare(judge: Judge, q: dict, text_a: str, text_b: str) -> Optional[dict]:
    user = (
        f"决策问题：{q['goal']}\n期望成果：{q['expected_outcome']}\n"
        f"约束：\n" + "\n".join(f"- {c}" for c in q["constraints"]) +
        f"\n\n【方案A】\n{text_a}\n\n【方案B】\n{text_b}"
    )
    return judge.ask_json(_JUDGE_SYSTEM, user, max_tokens=800)


def run_questions(questions: list[dict], workdir: Path) -> dict:
    judge = Judge()
    if not judge.available:
        raise SystemExit("需要 LLM_API_KEY（裁判回退 LLM_*）。无 key 请勿运行本评测。")
    results = []
    stats = {"treatment_win": 0, "baseline_win": 0, "tie": 0, "unparsed": 0}
    crit_delta = {c: [] for c in _CRITERIA}
    for q in questions:
        print(f"[{q['id']}] baseline ...", flush=True)
        base = _baseline_answer(q)
        print(f"[{q['id']}] committee pipeline ...", flush=True)
        treat, vote, err = _committee_answer(q, workdir)
        if not base or not treat:
            detail = "委员会未产出" + (f"：{err}" if err else "") if not treat else "基线未产出"
            results.append({"id": q["id"], "error": detail, "vote": vote})
            stats["unparsed"] += 1
            continue
        # 盲评：随机命名 A/B
        treatment_is_a = random.random() < 0.5
        text_a, text_b = (treat, base) if treatment_is_a else (base, treat)
        verdict = _judge_compare(judge, q, text_a, text_b)
        if not verdict or verdict.get("winner") not in ("A", "B", "tie"):
            results.append({"id": q["id"], "error": "裁判输出不可解析", "vote": vote})
            stats["unparsed"] += 1
            continue
        winner_raw = verdict["winner"]
        winner = ("treatment" if treatment_is_a else "baseline") if winner_raw != "tie" else "tie"
        stats["treatment_win" if winner == "treatment" else "baseline_win" if winner == "baseline" else "tie"] += 1
        for c in _CRITERIA:
            try:
                crit_delta[c].append(int(verdict[f"{c}_{'a' if treatment_is_a else 'b'}"]) - int(verdict[f"{c}_{'b' if treatment_is_a else 'a'}"]))
            except Exception:
                pass
        results.append({
            "id": q["id"], "goal": q["goal"], "treatment_is_a": treatment_is_a,
            "winner": winner, "judge_reason": verdict.get("reason", ""),
            "treatment_vote": vote,
        })
        print(f"[{q['id']}] winner={winner}", flush=True)
    crit_avg = {c: (round(sum(v) / len(v), 2) if v else None) for c, v in crit_delta.items()}
    return {"stats": stats, "criteria_delta_avg": crit_avg, "results": results,
            "total": len(questions), "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def _write_reports(report: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"decision-{ts}.json"
    md_path = out_dir / f"decision-{ts}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    s = report["stats"]
    lines = [
        "# 决策质量评测：单 LLM 直答 vs 委员会流程", "",
        f"- 题数：{report['total']}　委员会胜：**{s['treatment_win']}**　基线胜：{s['baseline_win']}　平：{s['tie']}　未解析：{s['unparsed']}",
        "- 四维均值差（委员会 − 基线，正数=委员会更好）：", "",
    ]
    for c, d in report["criteria_delta_avg"].items():
        lines.append(f"  - {c}: {d}")
    lines += ["", "| 题目 | 目标 | 胜者 | 裁判理由 |", "|---|---|---|---|"]
    for r in report["results"]:
        if "error" in r:
            lines.append(f"| {r['id']} | - | ERROR | {r['error']} |")
        else:
            lines.append(f"| {r['id']} | {r['goal'][:24]} | {r['winner']} | {r['judge_reason'][:40]} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    load_env()
    import os

    os.environ.pop("V2_DEMO", None)  # 评测永远跑真实模式；离线请跑 test_decision_eval.py
    parser = argparse.ArgumentParser(description="决策质量评测（单 LLM vs 委员会流程）")
    parser.add_argument("--limit", type=int, default=len(QUESTIONS), help="只跑前 N 题")
    args = parser.parse_args()
    report = run_questions(QUESTIONS[: args.limit], Path(tempfile_workdir()))
    json_path, md_path = _write_reports(report, Path("evals/reports"))
    s = report["stats"]
    print(f"done: treatment {s['treatment_win']} - baseline {s['baseline_win']} - tie {s['tie']} "
          f"(unparsed {s['unparsed']})\n{json_path}\n{md_path}")
    return 0


def tempfile_workdir() -> str:
    return "data"


if __name__ == "__main__":
    raise SystemExit(main())
