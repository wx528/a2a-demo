# Web Debate Mode + Step Control — Design Spec

- Date: 2026-09-26
- Status: Approved (design confirmed in conversation)
- Scope: web meeting room only (backend + frontend) plus a small debate-agent input
  extension. Push notifications, auth, multi-room concurrent debates remain out
  of scope.

## 1. Goals

1. **Step mode (default)**: agents speak one turn at a time. Before each turn the
   UI pauses, showing the next speaker with a ▶ 继续 button; the user may
   interject a message first (it becomes context for the next speaker).
   Auto-play (current continuous behavior) remains available as a toggle.
2. **Debate mode in the web room**: persona debates (苏格拉底/休谟/康德/尼采/
   怀疑论工程师/风险投资人 + 裁判) with real A2A calls to debate-agent,
   citations rendered as links, judge verdict as a distinct card.

## 2. Architecture Change: Turn-Based Orchestration

Replace "run whole flow inside one SSE generator" with an explicit turn
scheduler. The frontend drives; one API call = exactly one agent turn.

### 2.1 New/Changed Endpoints (web/main.py)

- `POST /api/meetings/{id}/turns/next` → executes ONE turn; returns an SSE
  stream for that turn (`status` / `message` events, same shapes as today),
  ending with a final `turn_done` event whose payload is
  `{"done": bool, "next": {participant_id, name} | null}`.
- `GET /api/meetings/{id}/next-turn` → peek without executing:
  `{"done": bool, "next": {...} | null, "mode": ..., "auto_play": bool}`.
- `GET /api/personas` → debate persona list (id, name, style, avatar) from
  `debate.personas.PERSONAS` + avatar map.
- `POST /api/meetings/{id}/messages` (existing) — user interjections; the turn
  builder includes all user messages in the next speaker's context.
- `GET /api/meetings/{id}/events` — becomes a lightweight stream (init snapshot
  + keepalive only); it NO LONGER auto-runs any flow.
- `POST /api/meetings/{id}/run` — removed (superseded by turns/next).

### 2.2 Turn Scheduler

A pure function `next_turn(meeting) -> TurnSpec | None` derived from meeting
state (mode, message history, participants):

- **pipeline**: research → writing → review → code → summary → done.
  Nth occurrence rule: if a user message arrives after the flow completed, the
  sequence restarts with research (topic = last user message) — same semantics
  as today's `/run` re-trigger.
- **roundtable**: moderator opening → for round in 1..N: research, writing
  (forced), review, code, summary (each may PASS — a PASS consumes the turn but
  adds no message) → fallback research if nobody spoke → moderator closing →
  done. Determining "who's next" from history: count agent messages + PASS
  markers; PASS turns are recorded as a `type: "pass"` system message so the
  scheduler can count them.
- **debate**: for round in 1..N: PRO turn, CON turn; then judge; done.
  Opponent text for each turn = the other side's previous argument (from
  history); user messages since the last agent turn become `[观众质询/INQUIRY]`
  content for the next speaker.

TurnSpec: `{participant_id, kind: "agent"|"judge", input_text or debate_msg}`.

### 2.3 Auto vs Step

- Meeting gains `auto_play: bool` (default **False** = step mode), plus
  `pro_persona`, `con_persona` (debate mode).
- Backend does NOT loop; auto-play is the frontend calling `turns/next`
  repeatedly when `turn_done.done == false`. One toggle in the UI, persisted
  per meeting (PATCH `auto_play` optional — v1: set at creation only).

### 2.4 DB Migration (web/db.py)

- `meetings` table gains columns `auto_play INTEGER DEFAULT 0`,
  `pro_persona TEXT`, `con_persona TEXT`.
- Migration: on `init_db()`, `PRAGMA table_info(meetings)` → `ALTER TABLE
  meetings ADD COLUMN <col> <def>` for each missing column (idempotent).
- Existing meetings load with `auto_play=0` (step) — acceptable.

### 2.5 Debate Agent Input Extension (debate_agent/main.py)

- `parse_debate_input` gains a 5th optional section `[观众质询/INQUIRY]` →
  key `inquiry`.
- `compose_user_prompt` / `compose_argument` include 观众质询 as an extra
  block the debater must address. Unknown-section tolerance unchanged.
- web calls the agent with `build_turn_message(...)` + optional
  `\n[观众质询/INQUIRY]\n<user msg>` appended.

## 3. Frontend (web/static/index.html)

- Create dialog: mode select gains 辩论; when selected, shows 正方/反方
  persona dropdowns (from `GET /api/personas`) + rounds slider (reuse
  max_rounds, 1-3).
- Meeting view:
  - **Step bar** (when `!done` and `!auto_play`): "下一位发言：{name}" +
    [▶ 继续] button + inline input ("插入发言后自动继续").
  - **Auto mode**: after each `turn_done` with `done=false`, immediately call
    next; a [⏸ 切换为步进] button flips to step mode live.
  - Persona participants get avatar/name from personas (web keeps a small
    avatar map: socrates 🏛️, hume 🔍, kant ⚖️, nietzsche ⚡,
    skeptic_engineer 🛠️, vc 💰, judge 👨‍⚖️).
  - Judge message rendered with `type: "judge"` → distinct card style.
  - Citation links already render via the existing markdown pipeline.
- Old meetings list remains functional; old rows simply show as step mode.

## 4. Testing

- `test_web_turns.py` (new, TestClient against web app with spawned fallback
  agents, mirroring test_web.py's process pattern):
  1. pipeline step: `next-turn` reports research first; `turns/next` executes
     exactly one agent message; repeat 5× reaches done; user interjection
     between turns lands in history and restart-able flow works after done.
  2. debate step: sequence pro → con → judge for rounds=1; persona names in
     messages; user interjection becomes part of the next turn's input
     (asserted via debate-agent receiving INQUIRY — fallback-mode transcript
     need only preserve ordering).
  3. `GET /api/personas` returns 7 entries with avatars.
- `test_web.py` (existing): migrate its flow to the turn API (auto-mode loop),
  preserving its SSE assertions per turn.
- debate agent unit tests: `parse_debate_input` INQUIRY section; prompt
  includes 观众质询 block.
- Existing suites stay green; e2e debate CLI unaffected.

## 5. Documentation

- README.md / README.zh-CN.md: meeting-room section documents step mode
  (default) + auto toggle + debate mode (persona dropdown, rounds, inquiry).
- CHANGELOG Unreleased entry.
- `.env.example`: `DEBATE_AGENT_URL` note; compose web service gains
  `DEBATE_AGENT_URL=http://debate-agent:8003`.

## 6. Acceptance Criteria

1. New meeting (default) runs step-by-step; user can interject between any two
   turns; the next agent's reply visibly responds to the interjection (with a
   live LLM key).
2. Auto toggle drives the same meeting to completion without clicks.
3. Debate mode: persona vs persona over N rounds + judge card; works both step
   and auto; citations clickable with a key.
4. Old meetings (pre-migration rows) still open and list correctly.
5. All suites green; ruff clean; LLM Smoke unaffected.
