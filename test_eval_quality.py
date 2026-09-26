"""质量评测层单元测试：辩题集、转录指标、judge 解析。"""

import asyncio
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evals.quality import metrics
from evals.quality.judge import (
    Judge,
    extract_json,
    judge_claim_support,
    judge_persona_adherence,
)
from evals.quality.motions import MOTIONS, get_motions


TRANSCRIPT = """# 辩论：测试

## 第 1 手 · 苏格拉底（正方）

论点甲 [来源1](https://good.example.com/a)。
论点乙没有引用。

## 第 2 手 · 休谟（反方）

（注意：本次未能检索到可靠外部来源，以下内容为未查证推演。）
对手的因果推断不成立。

## 裁判总结 · 裁判

双方表现持平。
"""


def test_motions_sanity():
    assert len(MOTIONS) == 15
    ids = [m["id"] for m in MOTIONS]
    assert len(set(ids)) == 15
    traps = [m for m in MOTIONS if m.get("trap")]
    assert len(traps) >= 2
    assert all(m["text"] and m["domain"] for m in MOTIONS)
    assert get_motions(["m01", "t01"]) == [MOTIONS[0], traps[0]]
    assert len(get_motions()) == 15


def test_parse_turns_excludes_judge():
    turns = metrics.parse_turns(TRANSCRIPT)
    assert len(turns) == 2
    assert "苏格拉底" in turns[0]["header"]
    assert metrics.has_declaration(turns[1]["text"])  # 休谟轮带无据声明
    assert all("裁判总结" not in t["header"] for t in turns)


def test_citation_coverage_math():
    turns = metrics.parse_turns(TRANSCRIPT)
    rate, cited, declared = metrics.citation_coverage(turns)
    assert cited == 1 and declared == 1
    assert rate == 1.0  # 1 cited + 1 declared over 2 turns
    assert metrics.citation_coverage([]) == (0.0, 0, 0)


def test_citation_coverage_union_not_double_counted():
    both = "论点 [来源](https://u.com)，另有一段（未查证推演）。"
    neither = "纯观点，无引用无声明。"
    turns = [{"header": "h1", "text": both}, {"header": "h2", "text": neither}]
    rate, cited, declared = metrics.citation_coverage(turns)
    assert rate == 0.5  # 同轮引用+声明只算一次，未覆盖轮不计
    assert cited == 1 and declared == 1


def test_turn_citations_and_declaration():
    assert metrics.turn_citations("a [x](https://u.com) b [y](http://v.cn)") == [
        "https://u.com", "http://v.cn",
    ]
    assert metrics.turn_citations("no links") == []
    assert metrics.has_declaration("（未查证推演）")
    assert metrics.has_declaration("未能检索到可靠外部来源")
    assert not metrics.has_declaration("fully cited")


def test_markers_cover_agent_no_sources_note():
    from debate_agent.main import _NO_SOURCES_NOTE
    from evals.quality.metrics import DECLARATION_MARKERS
    assert any(m in _NO_SOURCES_NOTE for m in DECLARATION_MARKERS), \
        "debate agent's no-sources note no longer matches any declaration marker"


def test_liveness_with_mock_transport():
    def handler(request):
        if request.url.host == "good.com":
            return httpx.Response(200, text="real content")
        if request.url.host == "dead.com":
            return httpx.Response(404)
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    liveness = asyncio.run(
        metrics.check_liveness(
            ["https://good.com/a", "https://dead.com/b", "https://boom.com/c"],
            transport=transport,
        )
    )
    assert liveness["https://good.com/a"]["alive"] is True
    assert liveness["https://good.com/a"]["content"] == "real content"
    rate, dead = metrics.liveness_rate(liveness)
    assert rate == pytest.approx(1 / 3)
    assert set(dead) == {"https://dead.com/b", "https://boom.com/c"}
    assert metrics.liveness_rate({}) == (1.0, [])


def test_trap_honesty():
    assert metrics.trap_honesty(TRANSCRIPT) is True
    assert metrics.trap_honesty("# 辩论\n\n无声明内容") is False


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('前言 {"a": [1,2]} 后记') == {"a": [1, 2]}
    assert extract_json("not json at all") is None
    assert extract_json("") is None


def test_judge_env_fallback(monkeypatch):
    monkeypatch.delenv("JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("JUDGE_BASE_URL", raising=False)
    monkeypatch.delenv("JUDGE_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    j = Judge()
    assert j.self_judged is True
    assert j.model == "deepseek-flash"
    assert j.available is True

    monkeypatch.setenv("JUDGE_API_KEY", "sk-judge")
    monkeypatch.setenv("JUDGE_MODEL", "gpt-4o")
    j2 = Judge()
    assert j2.self_judged is False
    assert j2.model == "gpt-4o"

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("JUDGE_API_KEY", raising=False)
    j3 = Judge()
    assert j3.available is False


def test_judge_claim_support_parses_and_falls_back():
    j = Judge.__new__(Judge)  # 不走网络

    j.ask_json = lambda system, user, max_tokens=800: {
        "verdicts": [{"url": "https://u", "verdict": "supported"}]
    }
    out = judge_claim_support(
        "论点 [来源](https://u)", [{"url": "https://u", "snippet": "s"}], j
    )
    assert out[0]["verdict"] == "supported"

    j.ask_json = lambda system, user, max_tokens=800: None
    out2 = judge_claim_support(
        "论点 [来源](https://u)", [{"url": "https://u", "snippet": "s"}], j
    )
    assert out2[0]["verdict"] == "unparsed"


def test_persona_adherence_scores():
    j = Judge.__new__(Judge)
    j.ask_json = lambda system, user, max_tokens=800: {"score": 4}
    assert judge_persona_adherence("追问式", "那么……？", j) == 4
    j.ask_json = lambda system, user, max_tokens=800: {"score": 99}
    assert judge_persona_adherence("风格", "x", j) == 5  # clamp 到 1-5
    j.ask_json = lambda system, user, max_tokens=800: None
    assert judge_persona_adherence("风格", "x", j) == 0  # unparsed
