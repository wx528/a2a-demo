import pytest
from web.v2.agents_client import build_turn_prompt, AgentSpeakerBackend, AgentCallError
from web.v2.models import V2Task


def _task():
    return V2Task(id="t", goal_text="g", created_at=1.0, updated_at=1.0,
                  constraints=[{"text": "c1", "confirmed": True}])


class NullBroadcasterStub:
    def publish(self, *a, **k):
        pass


class CollectingBroadcaster:
    """收集全部广播事件，供断言「零发布」或「事件序列」。"""

    def __init__(self):
        self.events = []

    def publish(self, task_id, event, data):
        self.events.append((task_id, event, data))


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

        async def _stream_text(self, task, author, url, prompt, publish=True):
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

        async def _stream_text(self, task, author, url, prompt, publish=True):
            return "还是不行"

    task = V2Task(id="t9", goal_text="g", created_at=1.0, updated_at=1.0)
    ballot = asyncio.run(B().vote_direction(task, "ada"))
    assert ballot.verdict == "abstain"


@pytest.mark.asyncio
async def test_vote_direction_publishes_no_events(monkeypatch):
    """匿名性回归：投票期间零 turn_delta/turn_start/turn_done 发布，票内容不得流出。"""
    class JsonStream:
        def __init__(self, url):
            pass

        async def stream_deltas(self, text):
            for piece in ('{"verdict": ', '"approve", "confidence": 4, ', '"reason": "ok"}', ""):
                yield piece

    monkeypatch.setattr("web.v2.agents_client.A2AJSONRPCClient", JsonStream)
    bc = CollectingBroadcaster()
    be = AgentSpeakerBackend(bc)
    task = V2Task(id="t10", goal_text="g", created_at=1.0, updated_at=1.0)
    ballot = await be.vote_direction(task, "ada")
    assert ballot.verdict == "approve"
    assert bc.events == []  # 不发任何事件：无真实席位的增量、无起止标记


@pytest.mark.asyncio
async def test_speak_still_publishes_deltas(monkeypatch):
    """对照用例：正常发言路径仍发布 turn_delta（防止把 speak 一并静音）。"""

    class Plain:
        def __init__(self, url):
            pass

        async def stream_deltas(self, text):
            yield "一句足够长的发言标题\n"
            yield "正文增量继续"

    monkeypatch.setattr("web.v2.agents_client.A2AJSONRPCClient", Plain)
    bc = CollectingBroadcaster()
    be = AgentSpeakerBackend(bc)
    task = V2Task(id="t11", goal_text="g", created_at=1.0, updated_at=1.0)
    title, body, verified = await be.speak(task, "ada", "clarify_ada")
    assert title and body
    deltas = [data for _, event, data in bc.events if event == "turn_delta"]
    assert len(deltas) >= 2 and deltas[0]["author"] == "ada"
