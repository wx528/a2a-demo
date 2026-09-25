"""辩论编排器状态机测试（stub A2A 客户端，无真实网络）。"""

import os
import sys

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

    monkeypatch.setattr(run_debate, "A2AJSONRPCClient", lambda url: FlakyClient(url))
    try:
        run_debate.run_debate("辩题", "socrates", "hume", rounds=1, agent_url="http://x")
        raised = False
    except RuntimeError:
        raised = True
    assert raised
