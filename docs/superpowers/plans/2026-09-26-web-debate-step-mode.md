# Web Debate Mode + Step Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn-based meeting orchestration (step mode default + auto toggle) and persona debate mode in the web room, per `docs/superpowers/specs/2026-09-26-web-debate-step-mode-design.md`.

**Architecture:** Replace the single blocking SSE flow with an explicit turn scheduler (`web/turns.py`, pure sequence + cursor state) driven by `POST /api/meetings/{id}/turns/next` (one turn per call, SSE for that turn, ends with `turn_done`). Auto-play is the frontend looping; step mode waits for the user. Debate turns call debate-agent with bracketed messages incl. optional `[观众质询/INQUIRY]`.

**Tech Stack:** Python 3.11+ / FastAPI / SQLite / React (CDN, classic JSX runtime) / Tailwind / pytest.

## Global Constraints

- Default `auto_play=False` (step mode) per spec; auto mode must remain reachable via one UI toggle.
- `POST /api/meetings/{id}/run` is REMOVED; `/events` keeps only `init` snapshot + keepalive (no flow execution).
- Existing suites stay green: `uv run pytest test_a2a.py test_registry.py test_task_store.py test_search_tool.py test_debate_agent.py test_debate_flow.py test_conformance.py test_eval_quality.py test_eval_runner.py test_env.py -q`, `uv run python test_e2e.py`; `uv run ruff check .` clean (E402 ignored repo-wide).
- LLM-offline: web integration tests spawn research/writing/debate agents in fallback mode with `LLM_API_KEY=""` forced.
- Conventional commits; PowerShell 5.1 shell (`uv run ...`); files written UTF-8 LF (`newline='\n'`).

---

### Task 1: Debate Agent INQUIRY Section

**Files:**
- Modify: `debate_agent/main.py`
- Test: `test_debate_agent.py`

**Interfaces:**
- Consumes: existing `parse_debate_input`, `compose_user_prompt`, `compose_argument`, `stream_response`.
- Produces: `parse_debate_input(text) -> {"motion","persona","stance","opponent","inquiry"}` (new key, `""` when absent); user prompt includes an 观众质询 block when inquiry non-empty.

- [ ] **Step 1: Write failing tests**

Append to `test_debate_agent.py`:

```python
def test_parse_debate_input_inquiry_section():
    text = INPUT + "[观众质询/INQUIRY]\n请直接回应成本问题\n"
    parsed = parse_debate_input(text)
    assert parsed["inquiry"] == "请直接回应成本问题"
    assert parse_debate_input(INPUT)["inquiry"] == ""


def test_inquiry_flows_into_llm_prompt(monkeypatch):
    import debate_agent.main as m

    captured = {}

    def fake_llm(system, user, **kw):
        captured["user"] = user
        return "论点 [来源1](https://real.com)"

    monkeypatch.setattr(
        m, "web_search",
        lambda q, max_results=5: [{"title": "t", "url": "https://real.com", "snippet": "s"}],
    )
    monkeypatch.setattr(m, "call_llm", fake_llm)
    client = TestClient(app)
    text = INPUT + "[观众质询/INQUIRY]\n请回应就业结构数据\n"
    resp = client.post(
        "/rpc",
        json={
            "jsonrpc": "2.0", "id": 1, "method": "SendMessage",
            "params": {"message": _msg(text)},
        },
    )
    task = resp.json()["result"]
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    assert "观众质询" in captured["user"]
    assert "请回应就业结构数据" in captured["user"]
```

Note: `INPUT` and `_msg` already exist in `test_debate_agent.py` from the Task that created it (`INPUT` is the 4-section sample, `_msg(text)` wraps a message). If the helper names differ, read the file first and adapt the test code to the existing helpers verbatim — do not rename the existing helpers.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test_debate_agent.py -q -k inquiry`
Expected: 2 failed (no `inquiry` key / prompt lacks 观众质询)

- [ ] **Step 3: Implement**

In `debate_agent/main.py`:

`parse_debate_input` — add to the marker list:

```python
    for key, marker in [
        ("motion", r"\[(?:辩题/)?MOTION\]"),
        ("persona", r"\[(?:角色/)?PERSONA\]"),
        ("stance", r"\[(?:立场/)?STANCE\]"),
        ("opponent", r"\[(?:对手论点/)?OPPONENT_ARGUMENTS\]"),
        ("inquiry", r"\[(?:观众质询/)?INQUIRY\]"),
    ]:
```

and initialize `sections = {"motion": "", "persona": "", "stance": "", "opponent": "", "inquiry": ""}`.

`compose_user_prompt` — add the block after 对手论点:

```python
def compose_user_prompt(motion, persona, stance, opponent, sources, inquiry: str = "") -> str:
    inquiry_block = f"\n观众质询（必须回应）：\n{inquiry}\n" if inquiry else ""
    return (
        f"辩题：{motion}\n"
        f"你的人格：{persona or '中立辩手'}\n"
        f"你的立场：{stance or '正方'}\n\n"
        f"检索资料：\n{_format_sources(sources)}\n\n"
        f"对手此前论点：\n{opponent or '（无，本轮为开篇立论）'}\n"
        f"{inquiry_block}\n"
        "请输出本轮论点。"
    )
```

Update the two callers to pass `parsed.get("inquiry", "")`:
- `compose_argument(..., inquiry)` — add parameter `inquiry: str = ""` and forward.
- `stream_response`'s `compose_user_prompt(...)` call and `process_task`'s `compose_argument(...)` call — pass `parsed.get("inquiry", "")` (both already destructure `parsed`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test_debate_agent.py -q && uv run ruff check debate_agent/ test_debate_agent.py`
Expected: all passed, lint clean

- [ ] **Step 5: Commit**

```bash
git add debate_agent/main.py test_debate_agent.py
git commit -m "feat(debate): optional INQUIRY section for audience interjections"
```

---

### Task 2: Turn Scheduler and Backend Endpoints

**Files:**
- Create: `web/turns.py`, `test_web_scheduler.py`, `test_web_turns.py`
- Modify: `web/main.py`, `web/db.py`

**Interfaces:**
- Consumes: `debate.personas.PERSONAS`, `debate.run_debate.build_turn_message` (Task-1 INQUIRY appended by web), `A2AJSONRPCClient`, existing `run_agent_step`/`call_agent`/`add_message`/`build_meeting_context` in web/main.py.
- Produces (web/turns.py):
  - `PIPELINE_STEPS = ["research","writing","review","code","summary"]`, `ROUNDTABLE_AGENTS = ["research","writing","review","code","summary"]`
  - `build_sequence(mode: str, max_rounds: int) -> List[Tuple[str, str]]` — pipeline: `[("agent", k) ...]`; roundtable: `[("agent","moderator")] + [("agent", k) per k per round] + [("fallback","research"), ("agent","moderator")]`; debate: `[("debate","pro"),("debate","con")] * rounds + [("judge","judge")]`
  - `next_turn(meeting) -> Tuple[Optional[dict], dict]` — returns `(spec|None, new_turn_state)`; spec `{"kind","key","index"}`; never mutates the meeting. Pipeline restart: when exhausted and the last non-system message is from `user`, resets cursor with `topic_override`.
  - `skip_fallback(seq, index, meeting) -> bool` — True when seq[index] is `("fallback", ...)` and any ROUNDTABLE_AGENTS message exists after the opening moderator message.
  - web/main.py: `Meeting` gains `auto_play: bool = False`, `pro_persona: str = ""`, `con_persona: str = ""`, `turn_state: Dict = {}`; `POST /api/meetings/{id}/turns/next` (SSE: status/message/system + final `turn_done` `{"done", "next"}`); `GET /api/meetings/{id}/next-turn`; `GET /api/personas`; `/run` removed; `/events` simplified to init + keepalive; `CreateMeetingRequest` gains `auto_play`, `pro_persona`, `con_persona`; `DEBATE_AGENT_URL` env (default `http://localhost:8003`).

- [ ] **Step 1: Write failing scheduler tests**

Create `test_web_scheduler.py`:

```python
"""web/turns.py 纯调度器测试：三种模式的序列与游标推进，无需起服务。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web.turns import build_sequence, next_turn, skip_fallback, PIPELINE_STEPS


def _meeting(mode="pipeline", max_rounds=1, messages=None, turn_state=None,
             pro="socrates", con="hume"):
    from web.main import Meeting, Participant, ChatMessage
    parts = [Participant(id="user", name="你", role="user", avatar="👤")]
    return Meeting(
        id="t1", topic="辩题X", mode=mode, max_rounds=max_rounds,
        created_at="12:00:00", participants=parts,
        messages=messages or [], status="active",
        pro_persona=pro, con_persona=con,
        turn_state=turn_state or {},
    )


def _msg(pid, mtype="message"):
    from web.main import ChatMessage
    return ChatMessage(
        id=f"m-{pid}-{mtype}-{_msg.n}", meeting_id="t1", participant_id=pid,
        participant_name=pid, role="agent", content="c", timestamp="12:00:00",
        type=mtype,
    )
_msg.n = 0
```

(If giving `_msg` an attribute fails lint, use a module-level counter variable instead.)

```python
def test_build_sequence_shapes():
    assert build_sequence("pipeline", 1) == [("agent", k) for k in PIPELINE_STEPS]
    rt = build_sequence("roundtable", 2)
    assert rt[0] == ("agent", "moderator") and rt[-1] == ("agent", "moderator")
    assert ("fallback", "research") in rt
    assert len(rt) == 1 + 10 + 2
    db = build_sequence("debate", 2)
    assert db == [("debate", "pro"), ("debate", "con")] * 2 + [("judge", "judge")]


def test_pipeline_walk_and_done_then_restart():
    m = _meeting(mode="pipeline")
    seen = []
    for _ in range(5):
        spec, st = next_turn(m)
        assert spec is not None
        seen.append(spec["key"])
        m.turn_state = st
    assert seen == PIPELINE_STEPS
    spec, _ = next_turn(m)
    assert spec is None  # done
    # 用户在结束后发言 -> 重启，主题切换为用户消息
    _msg.n += 1
    m.messages.append(_msg("user"))
    spec, st = next_turn(m)
    assert spec == {"kind": "agent", "key": "research", "index": 0}
    assert st["topic_override"] == "c"


def test_debate_sequence_and_done():
    m = _meeting(mode="debate", max_rounds=2)
    order = []
    for _ in range(5):
        spec, st = next_turn(m)
        order.append((spec["kind"], spec["key"]))
        m.turn_state = st
    assert order == [("debate", "pro"), ("debate", "con")] * 2 + [("judge", "judge")]
    spec, _ = next_turn(m)
    assert spec is None


def test_skip_fallback_when_someone_spoke():
    m = _meeting(mode="roundtable", max_rounds=1)
    seq = build_sequence("roundtable", 1)
    fb_index = seq.index(("fallback", "research"))
    assert skip_fallback(seq, fb_index, m) is False  # 无人发言：不跳过（执行保底步）
    _msg.n += 1
    m.messages.append(_msg("research"))
    assert skip_fallback(seq, fb_index, m) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test_web_scheduler.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.turns'`

- [ ] **Step 3: Implement `web/turns.py`**

```python
"""
会议室轮次调度器（纯函数）。

序列 + 游标（turn_state.seq_index）驱动三种模式；游推进由执行器持久化。
pipeline 耗尽后若最后一条非系统消息来自用户，则重置游标并切换主题
（对应旧 /run 的重新触发语义）。
"""

import os
import sys
from typing import Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PIPELINE_STEPS = ["research", "writing", "review", "code", "summary"]
ROUNDTABLE_AGENTS = ["research", "writing", "review", "code", "summary"]


def build_sequence(mode: str, max_rounds: int) -> List[Tuple[str, str]]:
    if mode == "roundtable":
        seq = [("agent", "moderator")]
        for _ in range(max(1, max_rounds)):
            seq += [("agent", k) for k in ROUNDTABLE_AGENTS]
        seq += [("fallback", "research"), ("agent", "moderator")]
        return seq
    if mode == "debate":
        seq = []
        for _ in range(max(1, max_rounds)):
            seq += [("debate", "pro"), ("debate", "con")]
        return seq + [("judge", "judge")]
    return [("agent", k) for k in PIPELINE_STEPS]


def _last_non_system(meeting) -> Optional[object]:
    for m in reversed(meeting.messages):
        if m.type != "system":
            return m
    return None


def next_turn(meeting) -> Tuple[Optional[Dict], Dict]:
    """返回 (spec|None, 新 turn_state)。spec = {"kind","key","index"}。"""
    seq = build_sequence(meeting.mode, meeting.max_rounds)
    state: Dict = dict(meeting.turn_state or {})
    index = int(state.get("seq_index", 0))

    if index >= len(seq):
        last = _last_non_system(meeting)
        if meeting.mode == "pipeline" and last is not None and last.participant_id == "user":
            state = {"seq_index": 0, "topic_override": last.content}
            index = 0
        else:
            return None, state

    kind, key = seq[index]
    return {"kind": kind, "key": key, "index": index}, state


def skip_fallback(seq, index: int, meeting) -> bool:
    """roundtable 保底步：开场之后已有讨论 agent 发过言则跳过。"""
    if seq[index] != ("fallback", "research"):
        return False
    return any(
        m.participant_id in ROUNDTABLE_AGENTS for m in meeting.messages
    )


def advance(meeting, steps: int = 1) -> Dict:
    """执行器调用：游标前进步数（fallback 被跳过时为 2）。"""
    state: Dict = dict(meeting.turn_state or {})
    if "topic_override" in state and state.get("seq_index", 0) > 0:
        state.pop("topic_override", None)
    state["seq_index"] = int(state.get("seq_index", 0)) + steps
    return state
```

Note: `next_turn`'s restart branch writes the new cursor into the returned state but does NOT advance past index 0 — the executor advances after running index 0. Verify the test expectation `spec == {"kind": "agent", "key": "research", "index": 0}` matches this.

- [ ] **Step 4: DB migration (web/db.py)**

In `init_db()`, after the `executescript`, add idempotent column migration:

```python
def _migrate(conn):
    """为旧库补新列（幂等）。"""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(meetings)")}
    additions = {
        "auto_play": "INTEGER DEFAULT 0",
        "pro_persona": "TEXT DEFAULT ''",
        "con_persona": "TEXT DEFAULT ''",
        "turn_state": "TEXT DEFAULT '{}'",
    }
    for col, decl in additions.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE meetings ADD COLUMN {col} {decl}")
    conn.commit()
```

Call `_migrate(conn)` inside `init_db` (before closing). Update `save_meeting` INSERT to include the four columns (turn_state stored as `json.dumps(meeting.get("turn_state") or {})`, ensure_ascii=False); update `list_meetings` SELECT to include `auto_play`; `get_meeting` uses `SELECT *` so rows come back automatically — decode `turn_state` JSON back to dict and coerce `auto_play` to bool in `get_meeting` before returning (guard `json.loads` with try/except → `{}`).

Add `import json` at the top of db.py.

- [ ] **Step 5: web/main.py model + endpoints**

Model changes:

```python
class Meeting(BaseModel):
    id: str
    topic: str
    mode: str = "pipeline"  # pipeline | roundtable | debate
    max_rounds: int = 1
    auto_play: bool = False  # 默认步进
    pro_persona: str = ""
    con_persona: str = ""
    turn_state: Dict = {}
    created_at: str
    participants: List[Participant]
    messages: List[ChatMessage]
    status: str = "active"
```

Add env + avatar map near the top (after `WRITING_AGENT_URL`):

```python
DEBATE_AGENT_URL = os.getenv("DEBATE_AGENT_URL", "http://localhost:8003")

PERSONA_AVATARS = {
    "socrates": "🏛️", "hume": "🔍", "kant": "⚖️", "nietzsche": "⚡",
    "skeptic_engineer": "🛠️", "vc": "💰", "judge": "👨‍⚖️",
}
```

Fix package import for TestClient use — right after the existing `sys.path.append(...)` line add:

```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

so `import db` resolves both when run as a script and when imported as `web.main`.

Import scheduler pieces:

```python
from debate.personas import PERSONAS
from debate.run_debate import build_turn_message
import turns
```

`create_meeting(...)` signature becomes:

```python
def create_meeting(topic: str, mode: str = "pipeline", max_rounds: int = 1,
                   auto_play: bool = False, pro_persona: str = "socrates",
                   con_persona: str = "hume") -> Meeting:
```

with debate participants:

```python
    if mode == "debate":
        pro = PERSONAS[pro_persona]; con = PERSONAS[con_persona]
        participants = [
            Participant(id="user", name="你", role="user", avatar="👤"),
            Participant(id=pro["id"], name=pro["name"], role="agent",
                        avatar=PERSONA_AVATARS.get(pro["id"], "🗣️")),
            Participant(id=con["id"], name=con["name"], role="agent",
                        avatar=PERSONA_AVATARS.get(con["id"], "🗣️")),
            Participant(id="judge", name="裁判", role="agent", avatar=PERSONA_AVATARS["judge"]),
        ]
    else:
        participants = [ ...existing list... ]
```

and `mode_text` gains: `elif mode == "debate": f"辩论模式（{pro['name']} vs {con['name']}，{max_rounds} 轮）"`, plus `auto_play=auto_play, pro_persona=pro_persona, con_persona=con_persona` on the Meeting constructor.

Debate turn helpers (web/main.py):

```python
def _side_argument(meeting, side: str) -> str:
    """取某一方最近一次发言（辩论上下文用）。"""
    pid = meeting.pro_persona if side == "pro" else meeting.con_persona
    for m in reversed(meeting.messages):
        if m.participant_id == pid and m.type == "message":
            return m.content[:2000]
    return ""


def _pending_inquiry(meeting) -> str:
    """自上一位 agent 发言后累积的用户消息（观众质询，最多取最近 2 条）。"""
    texts = []
    for m in meeting.messages:
        if m.participant_id == "user" and m.type == "message":
            texts.append(m.content)
        elif m.participant_id in (meeting.pro_persona, meeting.con_persona, "judge"):
            texts = []
    return "\n".join(texts[-2:])


async def call_debate_agent(message_text: str) -> str:
    client = A2AJSONRPCClient(DEBATE_AGENT_URL)
    try:
        task = await client.send_message(message_text)
    except Exception as e:
        return f"辩论 Agent 调用失败：{e}"
    for part in (task.get("artifacts") or [{}])[0].get("parts", []):
        if part.get("text"):
            return part["text"].split("</think>")[-1].strip()
    return "辩论 Agent 没有返回可用结果。"


async def run_turn(meeting_id: str):
    """执行恰好一轮发言，产出该轮 SSE 事件并以 turn_done 收尾。"""
    meeting = meetings[meeting_id]
    spec, new_state = turns.next_turn(meeting)
    if spec is None:
        yield sse_event("turn_done", {"meeting_id": meeting_id, "done": True, "next": None})
        return

    seq = turns.build_sequence(meeting.mode, meeting.max_rounds)
    steps = 1
    if spec["kind"] == "fallback" and turns.skip_fallback(seq, spec["index"], meeting):
        spec, new_state = turns.next_turn_with_index(meeting, spec["index"] + 1)  # helper below
        steps = 2
        if spec is None:
            yield sse_event("turn_done", {"meeting_id": meeting_id, "done": True, "next": None})
            return
    meeting.turn_state = new_state
    db_save_state(meeting_id, meeting.turn_state)  # helper below

    topic_override = meeting.turn_state.get("topic_override")
    topic = topic_override or meeting.topic

    if spec["kind"] in ("agent", "fallback"):
        async for event in _run_classic_step(meeting_id, spec, topic):
            yield event
    elif spec["kind"] in ("debate", "judge"):
        async for event in _run_debate_step(meeting_id, spec):
            yield event

    meeting.turn_state = turns.advance(meeting, steps)
    db_save_state(meeting_id, meeting.turn_state)

    nxt_spec, _ = turns.next_turn(meeting)
    nxt = None
    if nxt_spec:
        nxt = _participant_preview(meeting, nxt_spec)
    yield sse_event("turn_done", {"meeting_id": meeting_id, "done": nxt_spec is None, "next": nxt})
```

Add to web/turns.py the helper used above:

```python
def next_turn_with_index(meeting, index: int) -> Tuple[Optional[Dict], Dict]:
    state: Dict = dict(meeting.turn_state or {})
    seq = build_sequence(meeting.mode, meeting.max_rounds)
    if index >= len(seq):
        return None, state
    state["seq_index"] = index
    kind, key = seq[index]
    return {"kind": kind, "key": key, "index": index}, state
```

Helpers in web/main.py:

```python
def db_save_state(meeting_id: str, state: Dict):
    meetings[meeting_id].turn_state = state
    db.save_meeting(meetings[meeting_id].model_dump())


def _participant_preview(meeting, spec) -> Dict:
    if spec["kind"] == "judge":
        return {"participant_id": "judge", "name": "裁判", "avatar": PERSONA_AVATARS["judge"]}
    if spec["kind"] == "debate":
        pid = meeting.pro_persona if spec["key"] == "pro" else meeting.con_persona
        p = PERSONAS[pid]
        return {"participant_id": pid, "name": p["name"], "avatar": PERSONA_AVATARS.get(pid, "🗣️")}
    return {"participant_id": spec["key"], "name": AGENTS[spec["key"]]["name"],
            "avatar": AGENTS[spec["key"]]["avatar"]}
```

`_run_classic_step` — port the existing prompt builders; signature
`async def _run_classic_step(meeting_id, spec, topic)`:

- pipeline (`mode=="pipeline"` or `kind=="fallback"`): reuse the exact input texts from the old `run_meeting_flow` (`"请研究这个主题：{topic}"`, writing/review/code/summary variants), context = `build_meeting_context(meeting_id)` for steps after research; delegate to the existing `run_agent_step(meeting_id, key, input, context)`.
- roundtable: `spec["index"]` decomposes as `r = (index - 1) // 5`, `off = (index - 1) % 5`, `agent_key = ROUNDTABLE_AGENTS[off]` (import from turns). Index 0 = moderator opening (existing prompt). Non-first positions keep today's PASS-decide behavior: build the same decide-prompt (force_speak when `r == 0` and agent in `["research","writing"]`), call `call_agent` once; if response starts with PASS → emit a `type: "pass"` system message via `add_message(meeting_id, "system", f"{AGENTS[agent_key]['name']} 选择本轮 PASS", msg_type="pass")` + SSE `system` event; else emit status/message events exactly like the old flow (thinking → speaking → message → idle). Final moderator (last seq position) uses the existing closing prompt.
- fallback step: research with context (existing prompt).

`_run_debate_step` — `async def _run_debate_step(meeting_id, spec)`:

```python
async def _run_debate_step(meeting_id: str, spec):
    meeting = meetings[meeting_id]
    if spec["kind"] == "judge":
        pid, persona, stance = "judge", None, "裁判"
        opponent = "\n\n---\n\n".join(
            f"{m.participant_name}：{m.content[:2000]}"
            for m in meeting.messages if m.participant_id in (meeting.pro_persona, meeting.con_persona)
        )
    else:
        side = spec["key"]
        pid = meeting.pro_persona if side == "pro" else meeting.con_persona
        persona = PERSONAS[pid]
        stance = "正方" if side == "pro" else "反方"
        opponent = _side_argument(meeting, "con" if side == "pro" else "pro")

    update_participant_status(meeting_id, pid, "thinking")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": pid, "status": "thinking"})

    if persona is not None:
        msg_text = build_turn_message(meeting.topic, persona, stance, opponent)
    else:
        msg_text = (
            f"[辩题/MOTION] {meeting.topic}\n"
            f"[角色/PERSONA] 裁判（中立评审，逐条核对论据与引用）\n"
            f"[立场/STANCE] 裁判\n"
            f"[对手论点/OPPONENT_ARGUMENTS]\n{opponent}"
        )
    inquiry = _pending_inquiry(meeting)
    if inquiry and spec["kind"] != "judge":
        msg_text += f"\n[观众质询/INQUIRY]\n{inquiry}"

    result = await call_debate_agent(msg_text)

    update_participant_status(meeting_id, pid, "speaking")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": pid, "status": "speaking"})

    msg = add_message(meeting_id, pid, result, msg_type="judge" if spec["kind"] == "judge" else "message")
    yield sse_event("message", msg.model_dump())

    update_participant_status(meeting_id, pid, "idle")
    yield sse_event("status", {"meeting_id": meeting_id, "participant_id": pid, "status": "idle"})
```

Endpoint changes:

```python
class CreateMeetingRequest(BaseModel):
    topic: str
    mode: str = "pipeline"  # pipeline | roundtable | debate
    max_rounds: int = 1
    auto_play: bool = False
    pro_persona: str = "socrates"
    con_persona: str = "hume"


@app.post("/api/meetings")
async def create_meeting_api(req: CreateMeetingRequest):
    rounds_cap = 10 if req.mode == "roundtable" else 3
    max_rounds = max(1, min(rounds_cap, req.max_rounds)) if req.mode in ("roundtable", "debate") else 1
    meeting = create_meeting(
        req.topic, mode=req.mode, max_rounds=max_rounds,
        auto_play=req.auto_play, pro_persona=req.pro_persona, con_persona=req.con_persona,
    )
    return meeting.model_dump()


@app.get("/api/personas")
async def list_personas():
    return [
        {"id": p["id"], "name": p["name"], "style": p["style"],
         "avatar": PERSONA_AVATARS.get(p["id"], "🗣️")}
        for p in PERSONAS.values() if p["id"] != "judge"
    ]


@app.get("/api/meetings/{meeting_id}/next-turn")
async def peek_next_turn(meeting_id: str):
    if not _ensure_meeting_loaded(meeting_id):
        return {"error": "Meeting not found"}, 404
    meeting = meetings[meeting_id]
    spec, _ = turns.next_turn(meeting)
    return {
        "done": spec is None,
        "next": _participant_preview(meeting, spec) if spec else None,
        "mode": meeting.mode,
        "auto_play": meeting.auto_play,
    }


@app.post("/api/meetings/{meeting_id}/turns/next")
async def execute_next_turn(meeting_id: str):
    if not _ensure_meeting_loaded(meeting_id):
        return {"error": "Meeting not found"}, 404
    return StreamingResponse(run_turn(meeting_id), media_type="text/event-stream")
```

`/events`: delete the `if len(meeting.messages) == 1:` flow-running block and the trailing `while meeting.status == "active"` keepalive becomes `while True: await asyncio.sleep(15)` (keepalive; break silently on disconnect via try/except around the sleep is unnecessary — uvicorn cancels the generator). DELETE the `/run` endpoint and both old flow functions `run_meeting_flow` / `run_roundtable_flow` (their prompt logic moves into `_run_classic_step`).

- [ ] **Step 6: Write endpoint integration tests**

Create `test_web_turns.py` (pattern: spawn real agents in fallback mode like `test_web.py`; ports 8011/8012/8013 to avoid collisions, web app imported via TestClient):

```python
"""步进 API 集成测试：真实 agent（回退模式），TestClient 驱动 web。"""

import os
import subprocess
import sys
import time

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_OFFLINE = {"LLM_API_KEY": "", "LLM_BASE_URL": ""}


def _start(main_file, port):
    env = {**os.environ, **ENV_OFFLINE, "PORT": str(port), "HOST": "localhost"}
    return subprocess.Popen(
        [sys.executable, main_file], cwd=BASE_DIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


@pytest.fixture(scope="module")
def services():
    procs = [_start("research_agent/main.py", 8011),
             _start("writing_agent/main.py", 8012),
             _start("debate_agent/main.py", 8013)]
    with httpx.Client(trust_env=False, timeout=3) as c:
        for _ in range(60):
            try:
                if all(c.get(f"http://localhost:{p}/").status_code == 200
                       for p in (8011, 8012, 8013)):
                    break
            except Exception:
                pass
            time.sleep(0.5)
    os.environ["RESEARCH_AGENT_URL"] = "http://localhost:8011"
    os.environ["WRITING_AGENT_URL"] = "http://localhost:8012"
    os.environ["DEBATE_AGENT_URL"] = "http://localhost:8013"
    os.environ["TASK_DB"] = ""  # 内存存储，避免污染本地 data/
    os.environ.pop("TASK_DB", None)
    import importlib
    import web.main as web_main
    importlib.reload(web_main)
    yield web_main
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
```

Note: web/main.py reads `DB_PATH` from its own module at import (`db.init_db()` runs at app startup via lifespan). To keep tests from touching the real `data/meetings.db`, set `os.environ["A2A_WEB_DB"]` — Task 2 must also make db.py honor `A2A_WEB_DB` (default unchanged `data/meetings.db`):

```python
# web/db.py 顶部
DB_PATH = os.path.join(
    os.environ.get("A2A_WEB_DB_DIR")
    or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"),
    "meetings.db",
)
```

and in the fixture set `os.environ["A2A_WEB_DB_DIR"]` to `tmp_path` before importing web.main.

Tests (using the fixture; client = `TestClient(services.app)`):

```python
def _create(client, **kw):
    body = {"topic": "步进测试", "mode": "pipeline", **kw}
    return client.post("/api/meetings", json=body).json()


def _turn_events(client, mid):
    resp = client.post(f"/api/meetings/{mid}/turns/next")
    assert resp.status_code == 200
    events = []
    for block in resp.text.split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
        if ev:
            events.append((ev, data))
    return events


def test_personas_endpoint(services):
    client = TestClient(services.app)
    personas = client.get("/api/personas").json()
    ids = [p["id"] for p in personas]
    assert "socrates" in ids and "hume" in ids and "judge" not in ids
    assert all(p["avatar"] for p in personas)


def test_pipeline_step_by_step_with_interjection(services):
    client = TestClient(services.app)
    mid = _create(client)["id"]
    peek = client.get(f"/api/meetings/{mid}/next-turn").json()
    assert peek["next"]["participant_id"] == "research"
    assert peek["auto_play"] is False

    events = _turn_events(client, mid)
    kinds = [e for e in events if e[0] == "turn_done"]
    assert kinds, "turn must end with turn_done"
    # 恰好一条 agent 消息
    m = client.get(f"/api/meetings/{mid}").json()
    agent_msgs = [x for x in m["messages"] if x["participant_id"] == "research"]
    assert len(agent_msgs) == 1

    # 用户插话 -> 下一轮（writing）
    client.post(f"/api/meetings/{mid}/messages", json={"content": "补充：关注安全方面"})
    events = _turn_events(client, mid)
    m = client.get(f"/api/meetings/{mid}").json()
    assert any(x["participant_id"] == "writing" for x in m["messages"])


def test_debate_full_flow_step_mode(services):
    client = TestClient(services.app)
    mid = _create(client, mode="debate", pro_persona="socrates", con_persona="hume",
                  max_rounds=1)["id"]
    speakers = []
    for _ in range(3):
        peek = client.get(f"/api/meetings/{mid}/next-turn").json()
        if peek["done"]:
            break
        speakers.append(peek["next"]["participant_id"])
        _turn_events(client, mid)
    assert speakers == ["socrates", "hume", "judge"]
    m = client.get(f"/api/meetings/{mid}").json()
    judge_msgs = [x for x in m["messages"] if x["type"] == "judge"]
    assert judge_msgs and judge_msgs[0]["participant_id"] == "judge"
    peek = client.get(f"/api/meetings/{mid}/next-turn").json()
    assert peek["done"] is True
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest test_web_scheduler.py test_web_turns.py -q && uv run pytest test_debate_agent.py test_debate_flow.py -q && uv run ruff check .`
Expected: all passed, lint clean. Existing suites (`test_a2a.py` etc.) unaffected — run once: all green.

- [ ] **Step 8: Commit**

```bash
git add web/turns.py web/main.py web/db.py test_web_scheduler.py test_web_turns.py
git commit -m "feat(web): turn-based orchestration with step API, debate mode and personas endpoint"
```

---

### Task 3: Frontend, test_web Migration and Docs

**Files:**
- Modify: `web/static/index.html`, `test_web.py`, `docker-compose.yml`, `.env.example`, `README.md`, `README.zh-CN.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: Task 2 endpoints (`turns/next` POST SSE, `next-turn` peek, `/api/personas`, `auto_play` field, `type: "judge"` messages).
- Produces: UI with step bar + auto toggle + debate creation; `test_web.py` green against the new API.

- [ ] **Step 1: index.html — state and API glue**

Inside `App()`, after the existing useState block add:

```jsx
            const [personas, setPersonas] = useState([]);
            const [proPersona, setProPersona] = useState("socrates");
            const [conPersona, setConPersona] = useState("hume");
            const [autoPlay, setAutoPlay] = useState(false);
            const [turnInfo, setTurnInfo] = useState(null);   // {done, next}
            const [turnRunning, setTurnRunning] = useState(false);
            const autoPlayRef = useRef(false);
            autoPlayRef.current = autoPlay;
```

Replace `connectSSE` body's event handlers: keep only `init` (setMeeting) and `onerror`; remove `message`/`status`/`system` listeners (turn stream supplies them). After `init`, also fetch turn state:

```jsx
            const refreshTurn = async (meetingId) => {
                try {
                    const res = await fetch(`/api/meetings/${meetingId}/next-turn`);
                    if (!res.ok) return;
                    setTurnInfo(await res.json());
                } catch (e) { /* ignore */ }
            };
```

Call `refreshTurn(meetingId)` at the end of `connectSSE`'s init handler and in `openMeeting`/`createMeeting` after setting the meeting.

SSE-via-POST helper (React app has no EventSource for POST):

```jsx
            const applyTurnEvent = (ev, data, meetingId) => {
                if (ev === "message" || ev === "system") {
                    const msg = ev === "system"
                        ? { id: Date.now().toString(), meeting_id: meetingId,
                            participant_id: "system", participant_name: "系统",
                            role: "system", content: JSON.parse(data).content,
                            timestamp: new Date().toLocaleTimeString(), type: "system" }
                        : JSON.parse(data);
                    setMeeting(prev => ({ ...prev, messages: [...prev.messages, msg] }));
                } else if (ev === "status") {
                    const { participant_id, status } = JSON.parse(data);
                    setMeeting(prev => ({
                        ...prev,
                        participants: prev.participants.map(p =>
                            p.id === participant_id ? { ...p, status } : p),
                    }));
                }
            };

            const runNextTurn = async (meetingId) => {
                if (turnRunning) return;
                setTurnRunning(true);
                try {
                    const res = await fetch(`/api/meetings/${meetingId}/turns/next`, { method: "POST" });
                    const reader = res.body.getReader();
                    const decoder = new TextDecoder();
                    let buf = "";
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        buf += decoder.decode(value, { stream: true });
                        let idx;
                        while ((idx = buf.indexOf("\n\n")) >= 0) {
                            const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
                            let ev = null, data = null;
                            for (const line of block.split("\n")) {
                                if (line.startsWith("event: ")) ev = line.slice(7);
                                else if (line.startsWith("data: ")) data = line.slice(6);
                            }
                            if (ev === "turn_done") {
                                const payload = JSON.parse(data);
                                setTurnInfo(payload);
                                if (!payload.done && autoPlayRef.current) {
                                    setTimeout(() => runNextTurn(meetingId), 600);
                                }
                            } else {
                                applyTurnEvent(ev, data, meetingId);
                            }
                        }
                    }
                } finally {
                    setTurnRunning(false);
                }
            };
```

Load personas in the initial useEffect:

```jsx
                fetch('/api/personas').then(r => r.ok ? r.json() : []).then(setPersonas).catch(() => {});
```

Rewrite `sendMessage`: post the message (optimistic UI as today), then instead of the old `/run` EventSource block call `runNextTurn(meeting.id)` (works for both step interjection —插入后自动继续— and post-done restart).

- [ ] **Step 2: index.html — create dialog**

In the create-form JSX: mode select gains `<option value="debate">辩论模式（人格对抗 + 裁判）</option>`; show the rounds slider when `mode === "roundtable" || mode === "debate"` (max 10 for roundtable, max 3 for debate — set the input's max attribute accordingly); persona dropdowns when `mode === "debate"`:

```jsx
                                    {mode === "debate" && (
                                        <div className="mb-4 grid grid-cols-2 gap-3">
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700 mb-2">正方人格</label>
                                                <select value={proPersona} onChange={(e) => setProPersona(e.target.value)}
                                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                                                    {personas.map(p => <option key={p.id} value={p.id}>{p.avatar} {p.name}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700 mb-2">反方人格</label>
                                                <select value={conPersona} onChange={(e) => setConPersona(e.target.value)}
                                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500">
                                                    {personas.map(p => <option key={p.id} value={p.id}>{p.avatar} {p.name}</option>)}
                                                </select>
                                            </div>
                                        </div>
                                    )}
                                    <label className="flex items-center gap-2 mb-4 text-sm text-gray-700">
                                        <input type="checkbox" checked={autoPlay} onChange={(e) => setAutoPlay(e.target.checked)}
                                            className="w-4 h-4 accent-blue-600" />
                                        自动连播（默认步进，可随时插话）
                                    </label>
```

`createMeeting` body: `JSON.stringify({ topic, mode, max_rounds: maxRounds, auto_play: autoPlay, pro_persona: proPersona, con_persona: conPersona })`.

- [ ] **Step 3: index.html — room view step bar + judge card**

Insert between the participants strip and `<main>`:

```jsx
                                {turnInfo && !turnInfo.done && !turnInfo.next && null}
                                {turnInfo && !turnInfo.done && turnInfo.next && (
                                    <div className="bg-indigo-50 border-b border-indigo-100 px-6 py-3">
                                        <div className="max-w-5xl mx-auto flex items-center gap-3 text-sm">
                                            <span className="text-indigo-700 font-medium">
                                                下一位发言：{turnInfo.next.avatar} {turnInfo.next.name}
                                            </span>
                                            <button
                                                onClick={() => runNextTurn(meeting.id)}
                                                disabled={turnRunning}
                                                className="bg-indigo-600 text-white px-4 py-1.5 rounded-lg hover:bg-indigo-700 disabled:opacity-50 font-medium"
                                            >
                                                {turnRunning ? '发言中…' : '▶ 继续'}
                                            </button>
                                            {autoPlay ? (
                                                <button onClick={() => setAutoPlay(false)}
                                                    className="ml-auto text-gray-500 hover:text-gray-700">
                                                    ⏸ 切换为步进
                                                </button>
                                            ) : (
                                                <button onClick={() => { setAutoPlay(true); runNextTurn(meeting.id); }}
                                                    className="ml-auto text-gray-500 hover:text-gray-700">
                                                    ⏩ 自动连播
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                )}
```

Judge card styling — in the message bubble className chain, extend the agent branch:
`msg.type === 'judge' ? 'bg-amber-50 border-2 border-amber-300 shadow-md' : 'bg-white shadow-sm border'`, and its label row gains `<span className="ml-2 px-1.5 py-0.5 bg-amber-200 text-amber-800 rounded text-xs">裁判总结</span>` when `msg.type === 'judge'`.

Sidebar + header mode labels: `{m.mode === 'roundtable' ? ... : m.mode === 'debate' ? \`辩论 · \${m.max_rounds}轮\` : '流水线'}` (both places).

- [ ] **Step 4: Migrate `test_web.py`**

Read `test_web.py` fully first. Replace its flow assertions to drive turns: after creating a meeting (mode per its current test), call `POST /turns/next` repeatedly until `turn_done.done`, collecting `message` events; keep its existing SSE-event parsing helper if reusable. Keep its original assertions about agent speakers observed (`{'code','research','writing','review'}`) — with auto-drive they should still hold. The old `/run`-based logic must be gone.

- [ ] **Step 5: Docs and compose**

- `docker-compose.yml` web service environment gains `- DEBATE_AGENT_URL=http://debate-agent:8003` and `depends_on` gains `- debate-agent`.
- `.env.example`: note `DEBATE_AGENT_URL` (local default http://localhost:8003).
- README.md / README.zh-CN.md meeting-room sections: document step mode (default) + auto toggle + debate mode (personas, rounds 1-3, audience inquiry between turns).
- CHANGELOG Unreleased/Added entry describing turn-based step mode + web debate mode.

- [ ] **Step 6: Full verification**

```bash
uv run pytest test_a2a.py test_registry.py test_task_store.py test_search_tool.py test_debate_agent.py test_debate_flow.py test_conformance.py test_eval_quality.py test_eval_runner.py test_env.py test_web_scheduler.py test_web_turns.py -q
uv run python test_web.py
uv run python test_e2e.py
uv run ruff check .
```
Expected: all green, lint clean.

- [ ] **Step 7: Commit and push**

```bash
git add web/static/index.html test_web.py docker-compose.yml .env.example README.md README.zh-CN.md CHANGELOG.md
git commit -m "feat(web): step-mode UI, debate mode frontend, docs and compose wiring"
git push origin main
git push gitea main
```
