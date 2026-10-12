"""决策质量评测的离线测试：demo 模式端到端 + 盲评聚合（fake 裁判），不花真钱。"""

import importlib
import json

import pytest


@pytest.fixture()
def demo_env(tmp_path, monkeypatch):
    monkeypatch.setenv("V2_DEMO", "1")
    monkeypatch.setenv("V2_DEMO_TURN_DELAY", "0")
    monkeypatch.setenv("V2_DB", str(tmp_path / "v2.db"))
    monkeypatch.setenv("LLM_API_KEY", "test-key")  # Judge.available 需要；ask_json 已被 fake
    import web.v2.routes as v2_routes
    importlib.reload(v2_routes)
    yield


def test_run_questions_end_to_end_demo(demo_env, tmp_path, monkeypatch):
    """demo 流程当处理组、假直答当基线、假裁判：统计与报告结构正确。"""
    from evals.quality import decision_eval as de
    from evals.quality.judge import Judge

    monkeypatch.setattr(de, "_baseline_answer", lambda q: "基线建议：先试点。")
    monkeypatch.setattr(de.random, "random", lambda: 0.01)  # treatment 恒为方案A（0.01<0.5），fake 裁判恒判 A 胜
    monkeypatch.setattr(
        Judge, "ask_json",
        lambda self, system, user, max_tokens=800: {
            "constraint_adherence_a": 7, "constraint_adherence_b": 5,
            "risk_coverage_a": 6, "risk_coverage_b": 5,
            "executability_a": 7, "executability_b": 5,
            "coherence_a": 8, "coherence_b": 6,
            "winner": "A", "reason": "处理组更贴合约束",
        },
    )
    report = de.run_questions(de.QUESTIONS[:1], tmp_path)
    assert report["total"] == 1
    assert report["stats"]["treatment_win"] == 1
    r = report["results"][0]
    assert r["winner"] == "treatment" and r["treatment_vote"]["quorum"] == 4
    assert report["criteria_delta_avg"]["constraint_adherence"] == 2.0

    json_path, md_path = de._write_reports(report, tmp_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["stats"] == report["stats"]
    md = md_path.read_text(encoding="utf-8")
    assert "委员会胜" in md and "q01" in md
