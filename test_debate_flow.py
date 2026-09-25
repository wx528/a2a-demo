"""辩论编排器状态机测试（stub A2A 客户端，无真实网络）。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from debate import run_debate
from debate.personas import PERSONAS, get_persona


class StubClient:
    def __init__(self, url):
        self.url = url
        self.sent = []

    async def send_message(self, text):
        self.sent.append(text)
        return {"artifacts": [{"parts": [{"text": f"ARG#{len(self.sent)}"}]}]}


class HalfwayClient:
    """第 1 手成功，其后全部失败：用于验证中止时保留部分转录。"""

    def __init__(self, url):
        self.url = url
        self.calls = 0

    async def send_message(self, text):
        self.calls += 1
        if self.calls == 1:
            return {"artifacts": [{"parts": [{"text": "PRO-OK"}]}]}
        raise RuntimeError("agent down")


def test_personas_include_judge_and_philosophers():
    for pid in ["socrates", "hume", "kant", "nietzsche", "judge"]:
        assert pid in PERSONAS, pid
    p = get_persona("socrates")
    assert p["name"] and p["style"]


def test_build_turn_message_sections():
    msg = run_debate.build_turn_message("辩题X", get_persona("hume"), "反方", "对手说Y")
    assert "[辩题/MOTION] 辩题X" in msg
    assert "[角色/PERSONA]" in msg and "休谟" in msg
    assert "[立场/STANCE] 反方" in msg
    assert "对手说Y" in msg


def test_round_sequence_and_judge_last(monkeypatch):
    created = []

    def fake_client(url):
        c = StubClient(url)
        created.append(c)
        return c

    monkeypatch.setattr(run_debate, "A2AJSONRPCClient", fake_client)
    transcript = run_debate.run_debate("辩题", "socrates", "hume", rounds=2, agent_url="http://x")
    all_sent = [t for c in created for t in c.sent]
    assert len(all_sent) == 5, "2 rounds x 2 turns + judge"
    assert "[立场/STANCE] 正方" in all_sent[0]
    assert "[立场/STANCE] 反方" in all_sent[1]
    assert "[立场/STANCE] 正方" in all_sent[2]
    assert "[立场/STANCE] 反方" in all_sent[3]
    assert "裁判" in all_sent[4]
    assert "ARG#1" in transcript and "ARG#5" in transcript


def test_retry_once_then_abort(monkeypatch):
    class FlakyClient:
        def __init__(self, url):
            self.calls = 0

        async def send_message(self, text):
            self.calls += 1
            raise RuntimeError("agent down")

    flaky = FlakyClient("http://x")
    monkeypatch.setattr(run_debate, "A2AJSONRPCClient", lambda url: flaky)
    with pytest.raises(run_debate.DebateAborted) as excinfo:
        run_debate.run_debate("辩题", "socrates", "hume", rounds=1, agent_url="http://x")
    assert flaky.calls == run_debate.RETRIES + 1, "turn must retry once before abort"
    assert excinfo.value.transcript_so_far == "", "no turns completed -> empty partial"
    assert "agent down" in excinfo.value.reason


def test_abort_carries_partial_transcript(monkeypatch):
    halfway = HalfwayClient("http://x")
    monkeypatch.setattr(run_debate, "A2AJSONRPCClient", lambda url: halfway)
    with pytest.raises(run_debate.DebateAborted) as excinfo:
        run_debate.run_debate("辩题", "socrates", "hume", rounds=1, agent_url="http://x")
    partial = excinfo.value.transcript_so_far
    assert "PRO-OK" in partial, "completed turn must survive in partial transcript"
    assert "苏格拉底" in partial and "正方" in partial
    assert "裁判总结" not in partial, "judge verdict must be absent on abort"


def test_main_abort_prints_partial_and_returns_1(monkeypatch, capsys):
    monkeypatch.setattr(run_debate, "A2AJSONRPCClient", lambda url: HalfwayClient("http://x"))
    rc = run_debate.main(
        ["辩题", "--pro", "socrates", "--con", "hume",
         "--rounds", "1", "--agent-url", "http://x"]
    )
    assert rc == 1
    captured = capsys.readouterr()
    assert "PRO-OK" in captured.out, "partial transcript must be printed to stdout"
    assert "error:" in captured.err and "agent down" in captured.err
