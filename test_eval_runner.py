"""质量评测 runner 的纯函数测试（不跑真实辩论）。"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evals.quality import run_eval
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


def test_build_markdown_renders_error_rows():
    meta = {"date": "d", "git": "g", "llm_model": "m", "judge_model": "j", "self_judged": False}
    error_row = {"id": "m02", "motion": "失败辩题", "trap": False, "error": "agent down"}
    md = build_markdown(meta, aggregate([error_row]), [error_row])
    assert "m02" in md and "失败辩题" in md  # 错误行也能渲染，不抛 KeyError


FAKE_TRANSCRIPT = """# 辩论：测试

## 第 1 手 · 苏格拉底（正方）

（注意：本次未能检索到可靠外部来源，以下内容为未查证推演。）

## 第 2 手 · 休谟（反方）

反方观点。
"""


def test_run_motions_continues_after_failure(monkeypatch):
    def fake_run_debate(motion_text, pro, con, rounds, agent_url):
        if "MARKER" in motion_text:
            raise RuntimeError("agent down")
        return FAKE_TRANSCRIPT

    monkeypatch.setattr(run_eval, "run_debate", fake_run_debate)

    class _FakeJudge:
        available = False

    args = argparse.Namespace(pro="socrates", con="hume", rounds=1, agent_url="http://x")
    motions = [
        {"id": "m01", "text": "普通辩题", "trap": False},
        {"id": "m02", "text": "含 MARKER 的辩题", "trap": False},
    ]
    rows = run_eval.run_motions(motions, args, _FakeJudge())
    assert len(rows) == 2
    assert "citation_coverage" in rows[0]  # 第 1 题正常出指标
    assert rows[1]["error"]  # 第 2 题失败但记录错误行而非中断
