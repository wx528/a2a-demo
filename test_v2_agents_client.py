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


@pytest.mark.asyncio
async def test_empty_response_raises(monkeypatch):
    class Empty:
        def __init__(self, url):
            pass

        async def stream_deltas(self, text):
            yield ""

    monkeypatch.setattr("web.v2.agents_client.A2AJSONRPCClient", Empty)
    be = AgentSpeakerBackend(NullBroadcasterStub())
    with pytest.raises(AgentCallError):
        await be.speak(_task(), "ada", "clarify_ada")


@pytest.mark.asyncio
async def test_fallback_placeholder_raises(monkeypatch):
    class Fallback:
        def __init__(self, url):
            pass

        async def stream_deltas(self, text):
            yield "[研究员 Ada暂未能生成发言，请稍后重试]"

    monkeypatch.setattr("web.v2.agents_client.A2AJSONRPCClient", Fallback)
    be = AgentSpeakerBackend(NullBroadcasterStub())
    with pytest.raises(AgentCallError):
        await be.speak(_task(), "ada", "clarify_ada")


def test_vote_direction_parses_after_retry():
    """首次输出无 JSON、第二次有效：返回有效票（重试 1 次）。"""
    import asyncio
    from web.v2.models import Ballot, V2Task

    class B(AgentSpeakerBackend):
        def __init__(self, outputs):
            super().__init__(broadcaster=None)
            self.outputs = list(outputs)

        async def _stream_text(self, task, author, url, prompt):
            return self.outputs.pop(0)

    task = V2Task(id="t9", goal_text="g", created_at=1.0, updated_at=1.0)
    b = B(["我觉得还行", '{"verdict": "approve", "confidence": 4, "reason": "ok"}'])
    ballot = asyncio.run(b.vote_direction(task, "ada"))
    assert ballot.verdict == "approve"
    assert ballot == Ballot(verdict="approve", confidence=4, reason="ok")


def test_vote_direction_abstains_on_garbage():
    import asyncio
    from web.v2.models import V2Task

    class B(AgentSpeakerBackend):
        def __init__(self):
            super().__init__(broadcaster=None)

        async def _stream_text(self, task, author, url, prompt):
            return "还是不行"

    task = V2Task(id="t9", goal_text="g", created_at=1.0, updated_at=1.0)
    ballot = asyncio.run(B().vote_direction(task, "ada"))
    assert ballot.verdict == "abstain"
