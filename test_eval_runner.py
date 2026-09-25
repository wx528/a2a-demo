"""质量评测 runner 的纯函数测试（不跑真实辩论）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evals.quality.run_eval import aggregate, build_markdown

ROWS = [
    {"id": "m01", "motion": "题A", "trap": False, "turns": 2,
     "citation_coverage": 1.0, "link_liveness": 1.0,
     "claim_support_rate": 0.8, "persona_adherence": 4.0},
    {"id": "t01", "motion": "陷阱B", "trap": True, "turns": 2,
     "citation_coverage": 0.5, "link_liveness": 0.5,
     "claim_support_rate": None, "persona_adherence": None, "trap_honesty": True},
]


def test_aggregate_means_and_trap_rate():
    s = aggregate(ROWS)
    assert s["motions"] == 2
    assert s["citation_coverage"] == 0.75
    assert s["link_liveness"] == 0.75
    assert s["claim_support_rate"] == 0.8  # None 跳过
    assert s["persona_adherence"] == 4.0
    assert s["trap_pass_rate"] == 1.0


def test_aggregate_empty():
    assert aggregate([]) == {
        "motions": 0, "citation_coverage": None, "link_liveness": None,
        "claim_support_rate": None, "persona_adherence": None, "trap_pass_rate": None,
    }


def test_build_markdown_contains_everything():
    meta = {"date": "2026-09-26T00:00:00Z", "git": "abc1234",
            "llm_model": "deepseek-chat", "judge_model": "gpt-4o", "self_judged": False}
    s = aggregate(ROWS)
    md = build_markdown(meta, s, ROWS)
    for needle in ["abc1234", "deepseek-chat", "gpt-4o", "题A", "陷阱B",
                   "citation_coverage", "trap_pass_rate", "1.0"]:
        assert needle in md, needle
