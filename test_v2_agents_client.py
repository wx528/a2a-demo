import pytest
from web.v2.agents_client import build_turn_prompt, AgentSpeakerBackend, AgentCallError
from web.v2.models import V2Task


def _task():
    return V2Task(id="t", goal_text="g", created_at=1.0, updated_at=1.0,
                  constraints=[{"text": "c1", "confirmed": True}])


class NullBroadcasterStub:
    def publish(self, *a, **k):
        pass


def test_prompt_sections():
    p = build_turn_prompt(_task(), "ada", "clarify_ada")
    assert "[目标] g" in p and "[约束]" in p and "✓ c1" in p and "研究员" in p


def test_env_override(monkeypatch):
    monkeypatch.setenv("ROLE_AGENT_URLS", "ada=http://x:9")
    from web.v2 import agents_client as m
    m.reload_urls()
    assert m.ROLE_AGENTS["ada"] == "http://x:9"


@pytest.mark.asyncio
async def test_backend_retries_then_raises(monkeypatch):
    calls = {"n": 0}

    class Flaky:
        def __init__(self, url):
            pass

        async def stream_deltas(self, text):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise RuntimeError("boom")
            yield "x"

    monkeypatch.setattr("web.v2.agents_client.A2AJSONRPCClient", Flaky)
    be = AgentSpeakerBackend(NullBroadcasterStub())
    with pytest.raises(AgentCallError):
        await be.speak(_task(), "ada", "clarify_ada")
    assert calls["n"] == 2
