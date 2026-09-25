# Fact-Grounded Persona Debate Demo — Design Spec

- Date: 2026-09-26
- Status: Approved (design confirmed in conversation)
- Scope: v1 as described; MCP integration and web visualization are explicitly out of scope

## 1. Goal

Add a persona-based, fact-grounded debate demo to the a2a-demo repo, exercising the
existing A2A template stack (JSON-RPC, streaming, task store, dynamic discovery).
Debaters must ground claims in retrieved sources with citation links and explicitly
declare when evidence is missing instead of hallucinating.

## 2. Components

```
shared/search_tool.py      # search abstraction (new)
debate_agent/              # debate agent (new, reuses A2AJSONRPCServer)
  ├── main.py
  └── Dockerfile
debate/                    # debate orchestration (new)
  ├── personas.py          # persona library
  └── run_debate.py        # CLI orchestrator
```

## 3. Search Tool Layer (`shared/search_tool.py`)

API:

```python
def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]
# each item: {"title": ..., "url": ..., "snippet": ...}
```

- Provider selection via env vars, mirroring the `LLM_*` pattern:
  - default: DuckDuckGo (no API key, works out of the box)
  - `SEARCH_PROVIDER=tavily` + `SEARCH_API_KEY` (opt-in, higher quality)
- On any failure (no network, no key, provider down) return `[]` — never raise.
- Env knobs: `SEARCH_PROVIDER`, `SEARCH_API_KEY`, `SEARCH_MAX_RESULTS` (default 5).

## 4. Debate Agent (`debate_agent/`)

Reuses `A2AJSONRPCServer` wholesale: SendMessage/streaming/persistence/failure
fallback come for free. Input message text is a structured prompt (see 4.2).

### 4.1 Card

- name: `debate-agent`, skill id: `debate` (tags: `debate`, `argumentation`)
- capabilities: streaming=true (process_task_stream provided)
- `TASK_DB` supported like the other agents

### 4.2 Input Contract

The orchestrator composes a single text message:

```
[辩题/MOTION] ...
[角色/PERSONA] 苏格拉底（风格：追问式、承认无知...）
[立场/STANCE] 正方 / 反方
[对手论点/OPPONENT_ARGUMENTS]（可为空）
  1. ... [来源](url)
```

The agent parses these bracketed sections; unknown sections are ignored, missing
MOTION => task fails fast with a clear FAILED message.

### 4.3 process_task Flow

1. Parse input sections.
2. Generate 1-3 search queries from the motion + opponent claims (one LLM call,
   strict JSON output; on failure fall back to the motion itself as the query).
3. `web_search` each query, merge + dedupe by URL, cap total sources (8).
4. Compose argument with LLM under hard constraints (see 4.4).
5. Artifact: Markdown argument with citations; status COMPLETED.

If the sources list is empty: the artifact must be a short statement that no
reliable sources were found, plus whatever reasoning can be offered flagged as
"未查证推演" (unverified reasoning). No fabricated citations, ever.

### 4.4 System Prompt Constraints (hard rules)

- Ground every factual claim in the retrieved sources; cite as `[来源N](url)`.
- Distinguish fact statements from opinion/inference explicitly.
- If evidence is missing or contradictory, say so — never invent sources.
- Stay in persona for tone, not for facts.
- Output Markdown; keep argument within ~400 words per turn.

### 4.5 Streaming

`process_task_stream` yields the argument text incrementally (search happens
before the first yield; sources are fetched blocking in the worker thread).

## 5. Debate Orchestrator (`debate/run_debate.py`)

### 5.1 Persona Library (`debate/personas.py`)

Seed personas (id, name, style prompt): socrates, hume, kant, nietzsche,
skeptic_engineer (怀疑论工程师), vc (风险投资人). A neutral `judge` persona is
built-in (also uses search to verify the strongest claims).

### 5.2 Flow

```
motion -> PRO opening -> CON rebuttal -> PRO counter -> ... (rounds N)
       -> JUDGE verdict (weighs cited evidence on both sides)
```

- One round = one PRO turn followed by one CON turn. Round 1's PRO turn is the
  opening statement; later PRO/CON turns are rebuttals. `--rounds N` thus yields
  `2N` debater turns, then the judge verdict.

- Each turn sends the opponent's previous argument (with citations) in
  OPPONENT_ARGUMENTS.
- All calls go through `A2AJSONRPCClient` (real A2A traffic, exercises the stack).
- Turn failure (agent FAILED / network error): retry once, then abort with a
  partial transcript and non-zero exit code.

### 5.3 CLI

```
uv run python debate/run_debate.py "AI 会取代大多数工作吗" \
    --pro socrates --con hume --rounds 2 \
    [--agent-url http://localhost:8003] [--out transcript.md]
```

- Prints progress to stderr, final Markdown transcript to stdout (or `--out` file).
- Exit codes: 0 ok, 1 setup/agent failure, 2 usage error.

### 5.4 Compose

`debate-agent` service added to docker-compose.yml (port 8003, TASK_DB volume,
included in orchestrator `AGENT_URLS`).

## 6. Testing

- Unit (`test_search_tool.py`): provider selection, empty-result handling,
  never-raises property (mock provider errors). No-key CI path: DDG attempted,
  failures degrade to `[]`.
- Unit (`test_debate_agent.py`): input parsing, missing MOTION => FAILED with
  message, empty-sources artifact contains the no-reliable-sources statement and
  no fabricated URLs, system prompt contains grounding constraints.
- Unit (`test_debate_flow.py`): orchestrator state machine (turn order, judge last)
  against a stub A2A client class; retry-once behavior.
- E2E (`test_e2e.py` extension): spawn debate-agent, run a 1-round debate in LLM
  fallback mode — protocol must complete, transcript well-formed.
- LLM smoke (optional follow-up): one real 1-round debate asserting citations
  appear when search is available.

## 7. Documentation

- README (en) + README.zh-CN: new "Persona Debate Demo" section (setup, CLI
  example, sample transcript snippet).
- CHANGELOG entry under Unreleased.
- `.env.example`: SEARCH_PROVIDER / SEARCH_API_KEY / SEARCH_MAX_RESULTS.

## 8. Acceptance Criteria

1. `uv run python debate/run_debate.py "<motion>" --rounds 1` produces a
   transcript through real A2A calls.
2. With search available, factual claims in the transcript carry citation links.
3. With no search and no LLM key, the pipeline still completes in fallback mode
   (protocol correctness) — agents declare missing evidence rather than citing.
4. All existing tests stay green; ruff clean on new files.
