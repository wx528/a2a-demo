# Fact-Grounded Persona Debate Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persona-based, fact-grounded debate demo (search tool layer, debate agent, CLI orchestrator) on top of the existing A2A stack.

**Architecture:** A reusable `web_search()` abstraction in `shared/`; a `debate-agent` reusing `A2AJSONRPCServer` (blocking + streaming); a CLI orchestrator that runs PRO/CON turns and a judge through real `A2AJSONRPCClient` calls. Spec: `docs/superpowers/specs/2026-09-26-debate-demo-design.md`.

**Tech Stack:** Python 3.11+, FastAPI, httpx, Pydantic v2, ddgs (DuckDuckGo), Tavily REST (opt-in), uv, pytest.

## Global Constraints

- Python >= 3.11; deps managed in `pyproject.toml` (then `uv lock` / `uv sync`).
- Follow existing code conventions: agents = `process_task` + optional `process_task_stream`, sys.path bootstrap, Chinese docstrings/comments allowed.
- Never fabricate citations; search layer never raises (returns `[]`).
- Legacy A2A behavior must stay green: `uv run pytest test_a2a.py test_registry.py test_task_store.py -q`, `uv run python test_e2e.py`, `uv run python test_web.py`.
- `uv run ruff check <changed files>` clean.
- Commit style: conventional commits (`feat:`, `test:`, `docs:`, `chore:`).
- One round = PRO turn + CON turn; `--rounds N` = 2N turns then judge verdict.

---

### Task 1: Search Tool Layer

**Files:**
- Create: `shared/search_tool.py`
- Test: `test_search_tool.py`
- Modify: `pyproject.toml` (add `ddgs` dependency)

**Interfaces:**
- Consumes: nothing new (httpx already a dep).
- Produces: `web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]` where each item is `{"title": str, "url": str, "snippet": str}`; env knobs `SEARCH_PROVIDER` (`duckduckgo` default | `tavily`), `SEARCH_API_KEY`, `SEARCH_MAX_RESULTS` (int, default 5). Never raises.

- [ ] **Step 1: Add dependency**

In `pyproject.toml` `dependencies`, add `"ddgs>=9.0.0",` after the openai line, then run `uv lock && uv sync --extra dev`.

- [ ] **Step 2: Write failing tests**

Create `test_search_tool.py`:

```python
"""shared/search_tool.py 单元测试：provider 选择、失败降级、永不抛异常。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import search_tool


def test_returns_list_of_dicts_shape(monkeypatch):
    def fake_ddg(query, max_results):
        return [{"title": "t", "href": "https://x", "body": "s"}]

    monkeypatch.setattr(search_tool, "_search_duckduckgo", fake_ddg)
    results = search_tool.web_search("kubernetes", max_results=3)
    assert results == [{"title": "t", "url": "https://x", "snippet": "s"}]


def test_provider_selection_tavily(monkeypatch):
    called = {}

    def fake_tavily(query, max_results):
        called["q"] = query
        return [{"title": "t", "url": "https://t", "snippet": "s"}]

    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("SEARCH_API_KEY", "sk-test")
    monkeypatch.setattr(search_tool, "_search_tavily", fake_tavily)
    assert search_tool.web_search("q")[0]["url"] == "https://t"
    assert called["q"] == "q"


def test_never_raises_on_provider_error(monkeypatch):
    def boom(query, max_results):
        raise RuntimeError("network down")

    monkeypatch.setattr(search_tool, "_search_duckduckgo", boom)
    assert search_tool.web_search("anything") == []


def test_dedupe_and_cap(monkeypatch):
    def fake(query, max_results):
        return [
            {"title": "a", "href": "https://same", "body": "1"},
            {"title": "b", "href": "https://same", "body": "2"},
            {"title": "c", "href": "https://other", "body": "3"},
        ]

    monkeypatch.setattr(search_tool, "_search_duckduckgo", fake)
    results = search_tool.web_search("q", max_results=5)
    assert [r["url"] for r in results] == ["https://same", "https://other"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest test_search_tool.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.search_tool'`

- [ ] **Step 4: Implement `shared/search_tool.py`**

```python
"""
搜索工具层：给 agent 提供带链接的网络检索能力。

Provider 通过环境变量选择（对齐 LLM_* 的风格）：
    SEARCH_PROVIDER=duckduckgo（默认，无需 key）| tavily（需 SEARCH_API_KEY）
    SEARCH_MAX_RESULTS=5

任何失败（无网络 / 无 key / 服务不可用）一律返回空列表，绝不抛异常。
"""

import os
import warnings
from typing import Dict, List

import httpx


def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """检索并返回 [{"title", "url", "snippet"}]，按 URL 去重。失败返回 []。"""
    if not query or not query.strip():
        return []
    cap = int(os.getenv("SEARCH_MAX_RESULTS", "5") or 5)
    max_results = min(max_results, cap) if cap > 0 else max_results

    provider = os.getenv("SEARCH_PROVIDER", "duckduckgo").lower()
    try:
        if provider == "tavily":
            raw = _search_tavily(query, max_results)
        else:
            raw = _search_duckduckgo(query, max_results)
    except Exception as e:
        warnings.warn(f"web_search failed ({provider}): {e}")
        return []

    seen = set()
    results = []
    for item in raw:
        url = item.get("url") or item.get("href") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        results.append(
            {
                "title": item.get("title") or "",
                "url": url,
                "snippet": item.get("snippet") or item.get("body") or "",
            }
        )
    return results


def _search_duckduckgo(query: str, max_results: int) -> List[Dict[str, str]]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


def _search_tavily(query: str, max_results: int) -> List[Dict[str, str]]:
    api_key = os.getenv("SEARCH_API_KEY", "")
    if not api_key:
        warnings.warn("SEARCH_API_KEY not set; tavily search skipped")
        return []
    resp = httpx.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": query, "max_results": max_results},
        timeout=15.0,
        trust_env=False,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest test_search_tool.py -q`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add shared/search_tool.py test_search_tool.py pyproject.toml uv.lock
git commit -m "feat: pluggable web search tool layer (DuckDuckGo default, Tavily opt-in)"
```

---

### Task 2: Debate Agent

**Files:**
- Create: `debate_agent/main.py`, `debate_agent/Dockerfile`
- Test: `test_debate_agent.py`

**Interfaces:**
- Consumes: `A2AJSONRPCServer`, `call_llm`, `call_llm_stream` (shared.llm_client), `web_search` (shared.search_tool), models from shared.models.
- Produces:
  - `parse_debate_input(text: str) -> Dict[str, str]` with keys `motion`, `persona`, `stance`, `opponent` (missing sections -> `""`)
  - `build_system_prompt() -> str` (contains the hard grounding rules)
  - `gather_sources(motion: str, opponent: str) -> List[Dict[str, str]]` (1-3 queries via LLM JSON, dedupe by URL, cap 8)
  - `compose_argument(motion, persona, stance, opponent, sources) -> str` (LLM call, or no-LLM fallback)
  - `process_task(task, store)` / `stream_response(task, store)` wired into an app on port 8003 (env `PORT`)
  - Card: name `debate-agent`, skill id `debate` (tags: debate, argumentation), streaming=True

- [ ] **Step 1: Write failing tests**

Create `test_debate_agent.py`:

```python
"""debate_agent 协议与行为测试（TestClient，无真实端口）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient

from debate_agent.main import app, parse_debate_input, build_system_prompt


def _msg(text):
    return {
        "messageId": "m1",
        "role": "ROLE_USER",
        "parts": [{"text": text}],
    }


def _send(client, text):
    resp = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {"message": _msg(text)},
        },
    )
    assert resp.status_code == 200, resp.text
    rpc_resp = resp.json()
    assert rpc_resp.get("error") is None, rpc_resp
    return rpc_resp["result"]


INPUT = (
    "[辩题/MOTION] AI 会取代大多数工作吗\n"
    "[角色/PERSONA] 苏格拉底（追问式，承认无知）\n"
    "[立场/STANCE] 正方\n"
    "[对手论点/OPPONENT_ARGUMENTS]\n1. 自动化历史创造新岗位 [来源](https://a.com)\n"
)


def test_parse_debate_input_sections():
    parsed = parse_debate_input(INPUT)
    assert "AI" in parsed["motion"]
    assert "苏格拉底" in parsed["persona"]
    assert parsed["stance"] == "正方"
    assert "https://a.com" in parsed["opponent"]
    assert parse_debate_input("no sections")["motion"] == ""


def test_system_prompt_contains_grounding_rules():
    prompt = build_system_prompt()
    assert "来源" in prompt
    assert "不得编造" in prompt or "绝不编造" in prompt


def test_missing_motion_fails_fast(monkeypatch):
    import debate_agent.main as m

    monkeypatch.setattr(m, "call_llm", lambda *a, **k: None)
    client = TestClient(app)
    task = _send(client, "[角色/PERSONA] x\n[立场/STANCE] 正方")
    assert task["status"]["state"] == "TASK_STATE_FAILED"
    assert "辩题" in task["status"]["message"]["parts"][0]["text"]


def test_no_sources_no_llm_no_fabricated_links(monkeypatch):
    import debate_agent.main as m

    monkeypatch.setattr(m, "web_search", lambda q, max_results=5: [])
    monkeypatch.setattr(m, "call_llm", lambda *a, **k: None)
    client = TestClient(app)
    task = _send(client, INPUT)
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    text = task["artifacts"][0]["parts"][0]["text"]
    assert "](http" not in text, "must not fabricate citation links"
    assert "LLM 服务不可用" in text


def test_sources_flow_into_argument(monkeypatch):
    import debate_agent.main as m

    captured = {}

    def fake_llm(system, user, **kw):
        captured["system"] = system
        captured["user"] = user
        return "论点... [来源1](https://real.com)"

    monkeypatch.setattr(
        m, "web_search",
        lambda q, max_results=5: [{"title": "t", "url": "https://real.com", "snippet": "s"}],
    )
    monkeypatch.setattr(m, "call_llm", fake_llm)
    monkeypatch.setattr(
        m, "call_llm_stream",
        lambda system, user, **kw: iter(["chunk"]),
    )
    client = TestClient(app)
    task = _send(client, INPUT)
    text = task["artifacts"][0]["parts"][0]["text"]
    assert "https://real.com" in text
    assert "https://real.com" in captured["user"], "sources must be in the LLM prompt"


def test_agent_card_declares_debate_skill():
    client = TestClient(app)
    card = client.get("/.well-known/agent-card.json").json()
    assert card["name"] == "debate-agent"
    assert card["skills"][0]["id"] == "debate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test_debate_agent.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'debate_agent'`

- [ ] **Step 3: Implement `debate_agent/main.py`**

```python
"""
Debate Agent - 基于 A2A 协议的人格辩论 agent。
输入：带方括号段落标记的单条消息（辩题/人格/立场/对手论点）。
行为：检索资料 -> 基于资料与引用生成论点；无资料时明确声明，绝不编造来源。
"""

import json
import os
import re
import sys
from typing import Dict, Iterator, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.a2a_server import A2AJSONRPCServer, InMemoryTaskStore
from shared.llm_client import call_llm, call_llm_stream
from shared.models import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Role,
    Task,
    TaskState,
)
from shared.search_tool import web_search
from shared.task_store import SqliteTaskStore

AGENT_PORT = int(os.getenv("PORT", 8003))
AGENT_HOST = os.getenv("HOST", "localhost")
AGENT_URL = os.getenv("AGENT_URL", f"http://{AGENT_HOST}:{AGENT_PORT}")

MAX_SOURCES = 8
_NO_LLM_FALLBACK = "（当前 LLM 服务不可用，无法生成论点。）"
_NO_SOURCES_NOTE = "（注意：本次未能检索到可靠外部来源，以下内容为未查证推演。）"


def parse_debate_input(text: str) -> Dict[str, str]:
    """解析 [辩题/MOTION] 等方括号段落，未出现的段落返回空串。"""
    sections = {"motion": "", "persona": "", "stance": "", "opponent": ""}
    for key, marker in [
        ("motion", r"\[(?:辩题/)?MOTION\]"),
        ("persona", r"\[(?:角色/)?PERSONA\]"),
        ("stance", r"\[(?:立场/)?STANCE\]"),
        ("opponent", r"\[(?:对手论点/)?OPPONENT_ARGUMENTS\]"),
    ]:
        m = re.search(marker + r"\s*(.*?)(?=\n\[|\Z)", text, re.S)
        if m:
            sections[key] = m.group(1).strip()
    return sections


def build_system_prompt() -> str:
    return (
        "你是一场正式辩论中的辩手。必须遵守：\n"
        "1. 所有事实性论断必须基于提供的检索资料，并标注来源，格式 [来源N](url)。\n"
        "2. 明确区分事实陈述与观点推演（推演要标注'推演'）。\n"
        "3. 资料不足或相互矛盾时必须明说，绝不编造来源或数据。\n"
        "4. 人格只影响语气与论证风格，不影响事实。\n"
        "5. 输出 Markdown，单轮控制在 400 字以内，直接输出论点正文。"
    )


def generate_queries(motion: str, opponent: str) -> List[str]:
    """让 LLM 生成 1-3 个检索 query；失败时回退为辩题本身。"""
    prompt = (
        "针对下面的辩题和对手论点，生成 1-3 个用于事实核查的搜索 query。"
        '只输出 JSON 数组，如 ["query1","query2"]，不要输出其他内容。\n\n'
        f"辩题：{motion}\n对手论点：{opponent or '（无）'}"
    )
    raw = call_llm("你是搜索 query 生成器。", prompt, temperature=0.2, max_tokens=200)
    if raw:
        try:
            match = re.search(r"\[.*\]", raw, re.S)
            if match:
                queries = json.loads(match.group(0))
                queries = [str(q).strip() for q in queries if str(q).strip()]
                if queries:
                    return queries[:3]
        except (json.JSONDecodeError, ValueError):
            pass
    return [motion]


def gather_sources(motion: str, opponent: str) -> List[Dict[str, str]]:
    queries = generate_queries(motion, opponent)
    merged: List[Dict[str, str]] = []
    seen = set()
    for q in queries:
        for item in web_search(q, max_results=5):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            merged.append(item)
            if len(merged) >= MAX_SOURCES:
                return merged
    return merged


def _format_sources(sources: List[Dict[str, str]]) -> str:
    if not sources:
        return "（无检索资料）"
    lines = []
    for i, s in enumerate(sources, 1):
        lines.append(f"[来源{i}] {s['title']}\nURL: {s['url']}\n摘要: {s['snippet']}")
    return "\n\n".join(lines)


def compose_user_prompt(motion, persona, stance, opponent, sources) -> str:
    return (
        f"辩题：{motion}\n"
        f"你的人格：{persona or '中立辩手'}\n"
        f"你的立场：{stance or '正方'}\n\n"
        f"检索资料：\n{_format_sources(sources)}\n\n"
        f"对手此前论点：\n{opponent or '（无，本轮为开篇立论）'}\n\n"
        "请输出本轮论点。"
    )


def compose_argument(motion, persona, stance, opponent, sources) -> str:
    user_prompt = compose_user_prompt(motion, persona, stance, opponent, sources)
    result = call_llm(build_system_prompt(), user_prompt, max_tokens=1200)
    if result:
        text = result.split("</think>")[-1].strip()
        if not sources:
            text = _NO_SOURCES_NOTE + "\n\n" + text
        return text
    return _NO_LLM_FALLBACK


def _collect_user_text(task: Task) -> str:
    user_text = ""
    for msg in task.history:
        if msg.role == Role.USER:
            for part in msg.parts:
                if part.text:
                    user_text += part.text
    return user_text


def _prepare(task: Task):
    """解析输入并检索资料；缺辩题直接抛错（由框架兜底为 FAILED）。"""
    parsed = parse_debate_input(_collect_user_text(task))
    if not parsed["motion"]:
        raise ValueError("输入缺少 [辩题/MOTION] 段落")
    sources = gather_sources(parsed["motion"], parsed["opponent"])
    return parsed, sources


def process_task(task: Task, store: InMemoryTaskStore):
    store.update_status(task, TaskState.WORKING, "检索资料并构思论点...")
    parsed, sources = _prepare(task)
    argument = compose_argument(
        parsed["motion"], parsed["persona"], parsed["stance"], parsed["opponent"], sources
    )
    store.add_artifact(task, "argument", argument, "text/markdown")
    store.update_status(task, TaskState.COMPLETED, "论点完成")


def stream_response(task: Task, store: InMemoryTaskStore) -> Iterator[str]:
    store.update_status(task, TaskState.WORKING, "检索资料并构思论点...")
    parsed, sources = _prepare(task)
    user_prompt = compose_user_prompt(
        parsed["motion"], parsed["persona"], parsed["stance"], parsed["opponent"], sources
    )
    deltas = call_llm_stream(build_system_prompt(), user_prompt, max_tokens=1200)
    emitted = False
    if not sources:
        yield _NO_SOURCES_NOTE + "\n\n"
    if deltas is None:
        yield _NO_LLM_FALLBACK
        return
    try:
        for delta in deltas:
            if delta:
                emitted = True
                yield delta
    except Exception:
        return
    if not emitted:
        yield _NO_LLM_FALLBACK


agent_card = AgentCard(
    name="debate-agent",
    description="人格辩论 Agent，基于检索资料进行带引用的事实性辩论",
    supported_interfaces=[
        AgentInterface(
            url=f"{AGENT_URL}/rpc",
            protocol_binding="JSONRPC",
            protocol_version="1.0",
        )
    ],
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=True, push_notifications=False, extended_agent_card=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/markdown"],
    skills=[
        AgentSkill(
            id="debate",
            name="人格辩论",
            description="按人格与立场进行基于检索资料的辩论",
            tags=["debate", "argumentation"],
            examples=["辩题：AI 会取代大多数工作吗"],
            input_modes=["text/plain"],
            output_modes=["text/markdown"],
        )
    ],
)

TASK_DB = os.getenv("TASK_DB")
_task_store = SqliteTaskStore(TASK_DB) if TASK_DB else None

server = A2AJSONRPCServer(
    agent_card=agent_card,
    process_task=process_task,
    process_task_stream=stream_response,
    store=_task_store,
)
app = server.build_app(title="Debate Agent (A2A / JSON-RPC)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
```

- [ ] **Step 4: Create `debate_agent/Dockerfile`** (copy `research_agent/Dockerfile` verbatim, replace the COPY line for the agent dir):

```dockerfile
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv==0.5.9

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY shared/ ./shared/
COPY debate_agent/ ./debate_agent/

CMD ["python", "debate_agent/main.py"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest test_debate_agent.py -q && uv run ruff check debate_agent/ test_debate_agent.py`
Expected: 6 passed, lint clean

- [ ] **Step 6: Commit**

```bash
git add debate_agent/ test_debate_agent.py
git commit -m "feat: debate agent with fact-grounded argument generation"
```

---

### Task 3: Persona Library and Debate Orchestrator

**Files:**
- Create: `debate/personas.py`, `debate/run_debate.py`
- Test: `test_debate_flow.py`

**Interfaces:**
- Consumes: `A2AJSONRPCClient.send_message(text) -> task dict` (shared.a2a_client); orchestrator's `extract_agent_text` pattern (re-implemented locally in `debate/run_debate.py` as `artifact_text(task) -> str`).
- Produces:
  - `personas.PERSONAS: Dict[str, Persona]`; `Persona = Dict[str, str]` with keys `id`, `name`, `style`; `PERSONAS` includes `judge`
  - `personas.get_persona(pid: str) -> Dict[str, str]` (raises KeyError with available ids)
  - `debate.run_debate.build_turn_message(motion, persona, stance, opponent_text) -> str`
  - `debate.run_debate.run_debate(motion, pro_id, con_id, rounds, agent_url) -> str` (returns Markdown transcript; raises RuntimeError on agent failure after one retry)
  - `debate.run_debate.main(argv=None) -> int` (CLI entry; exit 0/1/2)

- [ ] **Step 1: Write failing tests**

Create `test_debate_flow.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test_debate_flow.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'debate'`

- [ ] **Step 3: Implement `debate/personas.py`**

```python
"""辩论人格库：哲学家 + 现代角色 + 中立裁判。"""

from typing import Dict, List

PERSONAS: Dict[str, Dict[str, str]] = {
    "socrates": {
        "id": "socrates",
        "name": "苏格拉底",
        "style": "追问式论证，坦承无知，用连环反问逼近矛盾；语气平和而锐利",
    },
    "hume": {
        "id": "hume",
        "name": "休谟",
        "style": "经验主义怀疑论，只承认可观察证据，警惕归纳跳跃，常用'我们真的观察到...了吗'句式",
    },
    "kant": {
        "id": "kant",
        "name": "康德",
        "style": "义务论与先验框架，区分现象与物自体，论证结构严密，喜欢界定概念后推演",
    },
    "nietzsche": {
        "id": "nietzsche",
        "name": "尼采",
        "style": "视角主义，质疑流行道德预设，语言有冲击力，善用格言与价值重估",
    },
    "skeptic_engineer": {
        "id": "skeptic_engineer",
        "name": "怀疑论工程师",
        "style": "只认数据与工程现实，动辄要求量化指标、失败模式与边际成本分析",
    },
    "vc": {
        "id": "vc",
        "name": "风险投资人",
        "style": "市场与激励视角，关注采用曲线、单位经济与二阶效应，习惯用历史类比下注",
    },
    "judge": {
        "id": "judge",
        "name": "裁判",
        "style": "中立评审，逐条核对双方论据链与引用质量，明确指出未查证的断言，最后给出判定与理由",
    },
}


def get_persona(pid: str) -> Dict[str, str]:
    try:
        return PERSONAS[pid]
    except KeyError:
        available: List[str] = sorted(PERSONAS)
        raise KeyError(f"unknown persona '{pid}', available: {available}") from None
```

- [ ] **Step 4: Implement `debate/run_debate.py`**

```python
"""
Debate CLI 编排器：正反方多轮对抗 + 裁判总结，全程走 A2A JSON-RPC。

用法：
    uv run python debate/run_debate.py "AI 会取代大多数工作吗" \
        --pro socrates --con hume --rounds 2 [--out transcript.md]
"""

import argparse
import asyncio
import os
import sys
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.a2a_client import A2AJSONRPCClient
from debate.personas import get_persona

DEFAULT_AGENT_URL = "http://localhost:8003"
RETRIES = 1


def artifact_text(task: dict) -> str:
    artifacts = task.get("artifacts") or []
    if not artifacts:
        return ""
    for part in artifacts[0].get("parts", []):
        if part.get("text"):
            return part["text"]
    return ""


def build_turn_message(motion: str, persona: dict, stance: str, opponent_text: str) -> str:
    return (
        f"[辩题/MOTION] {motion}\n"
        f"[角色/PERSONA] {persona['name']}（风格：{persona['style']}）\n"
        f"[立场/STANCE] {stance}\n"
        f"[对手论点/OPPONENT_ARGUMENTS]\n{opponent_text or '（无）'}"
    )


async def send_with_retry(client, message: str) -> str:
    last_error = None
    for _ in range(RETRIES + 1):
        try:
            task = await client.send_message(message)
            text = artifact_text(task)
            if text:
                return text
            last_error = RuntimeError("empty argument from debate-agent")
        except Exception as e:
            last_error = e
    raise RuntimeError(f"debate-agent failed after retry: {last_error}")


async def run_debate_async(motion, pro_id, con_id, rounds, agent_url) -> str:
    pro = get_persona(pro_id)
    con = get_persona(con_id)
    judge = get_persona("judge")
    client = A2AJSONRPCClient(agent_url)

    turns = []  # (persona_name, stance, argument_text)
    last_con = ""
    for r in range(1, rounds + 1):
        opponent_for_pro = last_con
        pro_text = await send_with_retry(
            client, build_turn_message(motion, pro, "正方", opponent_for_pro)
        )
        turns.append((pro["name"], "正方", pro_text))

        con_text = await send_with_retry(
            client, build_turn_message(motion, con, "反方", pro_text)
        )
        turns.append((con["name"], "反方", con_text))
        last_con = con_text

    both = "\n\n---\n\n".join(f"{n}（{s}）：\n{t}" for n, s, t in turns)
    verdict = await send_with_retry(
        client,
        (
            f"[辩题/MOTION] {motion}\n"
            f"[角色/PERSONA] {judge['name']}（风格：{judge['style']}）\n"
            f"[立场/STANCE] 裁判\n"
            f"[对手论点/OPPONENT_ARGUMENTS]\n{both}"
        ),
    )

    lines = [f"# 辩论：{motion}\n", f"- 正方：{pro['name']}", f"- 反方：{con['name']}", f"- 轮数：{rounds}\n"]
    for i, (name, stance, text) in enumerate(turns, 1):
        lines.append(f"## 第 {i} 手 · {name}（{stance}）\n\n{text}\n")
    lines.append(f"## 裁判总结 · {judge['name']}\n\n{verdict}\n")
    return "\n".join(lines)


def run_debate(motion, pro_id, con_id, rounds, agent_url) -> str:
    return asyncio.run(
        run_debate_async(motion, pro_id, con_id, rounds, agent_url)
    )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="A2A persona debate runner")
    parser.add_argument("motion", help="辩题")
    parser.add_argument("--pro", default="socrates", help="正方人格 id（默认 socrates）")
    parser.add_argument("--con", default="hume", help="反方人格 id（默认 hume）")
    parser.add_argument("--rounds", type=int, default=2, help="辩论轮数（默认 2）")
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL, help="debate-agent 地址")
    parser.add_argument("--out", default=None, help="转录输出到文件（默认打印 stdout）")
    args = parser.parse_args(argv)

    if args.rounds < 1:
        parser.error("--rounds must be >= 1")
        return 2

    try:
        transcript = run_debate(args.motion, args.pro, args.con, args.rounds, args.agent_url)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(transcript)
        print(f"transcript written to {args.out}", file=sys.stderr)
    else:
        print(transcript)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest test_debate_flow.py -q && uv run ruff check debate/ test_debate_flow.py`
Expected: 4 passed, lint clean

- [ ] **Step 6: Commit**

```bash
git add debate/ test_debate_flow.py
git commit -m "feat: persona library and CLI debate orchestrator with retry"
```

---

### Task 4: Compose Integration, E2E and Docs

**Files:**
- Modify: `docker-compose.yml`, `test_e2e.py`, `README.md`, `README.zh-CN.md`, `.env.example`, `CHANGELOG.md`

**Interfaces:**
- Consumes: debate agent (port 8003), `debate.run_debate`, existing e2e helpers.
- Produces: compose service `debate-agent`; e2e coverage; docs.

- [ ] **Step 1: Extend `test_e2e.py`**

After the existing orchestrator workflow test block (inside `main()`, before the final `print("\nAll e2e tests passed!")`), add:

```python
        # Test debate demo (fallback mode, protocol correctness)
        procs.append(start_service("debate", 8003, "debate_agent/main.py"))
        assert wait_for_ready("http://localhost:8003/"), "debate agent not ready"

        from debate.run_debate import run_debate as run_debate_lib

        transcript = run_debate_lib(
            "AI 会取代大多数工作吗", "socrates", "hume",
            rounds=1, agent_url="http://localhost:8003",
        )
        assert "苏格拉底" in transcript and "休谟" in transcript
        assert "裁判总结" in transcript
        print("[OK] debate demo (1 round, fallback mode)")
```

- [ ] **Step 2: Run e2e to verify it passes**

Run: `uv run python test_e2e.py`
Expected: `All e2e tests passed!` including `[OK] debate demo`

- [ ] **Step 3: Add compose service**

In `docker-compose.yml`, after `writing-agent`, add:

```yaml
  debate-agent:
    build:
      context: .
      dockerfile: debate_agent/Dockerfile
    ports:
      - "8003:8003"
    environment:
      - PORT=8003
      - HOST=debate-agent
      - LLM_API_KEY=${LLM_API_KEY:-}
      - LLM_BASE_URL=${LLM_BASE_URL:-}
      - LLM_MODEL=${LLM_MODEL:-gpt-4o-mini}
      - SEARCH_PROVIDER=${SEARCH_PROVIDER:-duckduckgo}
      - SEARCH_API_KEY=${SEARCH_API_KEY:-}
      - TASK_DB=/data/tasks.db
    volumes:
      - debate-agent-data:/data
    networks:
      - a2a-network
```

Update orchestrator `AGENT_URLS` default to `http://research-agent:8001,http://writing-agent:8002,http://debate-agent:8003`, add `- debate-agent` to its `depends_on`, and add `debate-agent-data:` to bottom `volumes:`.

- [ ] **Step 4: Update `.env.example`**

Append:

```bash
# ===========================================
# 辩论 Agent 搜索配置（可选）
# 默认 DuckDuckGo 无需 key；Tavily 需要申请 https://tavily.com
# ===========================================
# SEARCH_PROVIDER=tavily
# SEARCH_API_KEY=tvly-...
# SEARCH_MAX_RESULTS=5
```

- [ ] **Step 5: Update READMEs and CHANGELOG**

In both `README.md` (after the "Web Meeting Room Demo" section) and `README.zh-CN.md` (after "Web 会议室演示"), insert a matching section (English / Chinese respectively):

English:

```markdown
---

## Persona Debate Demo

A fact-grounded debate between personas (philosophers and modern archetypes).
Each turn: the `debate-agent` retrieves web sources, then argues with inline
citations; missing evidence is declared, never fabricated.

```bash
# start the debate agent (or docker compose up)
uv run python debate_agent/main.py &

uv run python debate/run_debate.py "Will AI replace most jobs?" \
    --pro socrates --con hume --rounds 2
```

Personalities: `socrates`, `hume`, `kant`, `nietzsche`,
`skeptic_engineer`, `vc`. Search works out of the box via DuckDuckGo;
set `SEARCH_PROVIDER=tavily` + `SEARCH_API_KEY` for higher quality.
```

Chinese equivalent for `README.zh-CN.md`, plus update both "Project Structure"/"目录结构" trees to include `debate_agent/` and `debate/`.

`CHANGELOG.md` under `## [Unreleased]` → `### Added`:

```markdown
- 人格辩论 Demo：`debate-agent`（检索资料 + 引用论证，无资料明说绝不编造）与 CLI 编排器 `debate/run_debate.py`（苏格拉底/休谟/康德/尼采/怀疑论工程师/风险投资人 + 中立裁判，多轮对抗 + 判定）
- 搜索工具层 `shared/search_tool.py`：默认 DuckDuckGo 免 key，可选 Tavily（`SEARCH_PROVIDER`/`SEARCH_API_KEY`），任何失败降级为空结果
- docker-compose 新增 `debate-agent` 服务（8003 端口，SQLite 持久化卷）
```

- [ ] **Step 6: Full verification**

Run all:
```bash
uv run pytest test_a2a.py test_registry.py test_task_store.py test_search_tool.py test_debate_agent.py test_debate_flow.py -q
uv run python test_e2e.py
uv run python test_web.py
uv run ruff check .
```
Expected: all green, lint clean.

- [ ] **Step 7: Commit and push**

```bash
git add docker-compose.yml test_e2e.py README.md README.zh-CN.md .env.example CHANGELOG.md
git commit -m "feat: wire debate demo into compose, e2e and docs"
git push origin main
git push gitea main
```
