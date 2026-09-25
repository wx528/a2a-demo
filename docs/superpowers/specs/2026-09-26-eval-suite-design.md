# A2A Evaluation Suite (Conformance + Quality) — Design Spec

- Date: 2026-09-26
- Status: Approved (design confirmed in conversation)
- Scope: two tiers as described; public benchmark datasets (GAIA, tau-bench, etc.) are
  explicitly out of scope — we borrow their ideas (curated sets, judge scoring,
  liveness checking), not their infrastructure.

## 1. Goal

Give the a2a-demo repo a reusable evaluation capability:
1. **Tier 1 — Protocol conformance suite**: deterministic, offline, free. Runs
   against any live A2A agent URL, scores spec-compliance behaviors, outputs a
   report. Doubles as an acceptance tool for any A2A implementation built on
   this template.
2. **Tier 2 — Debate quality evals**: LLM-as-judge scoring of debate output
   grounding (citation coverage, link liveness, claim support, trap-motion
   honesty, persona adherence), with an independent judge model.

## 2. Structure

```
evals/
├── conformance/
│   ├── suite.py          # CLI runner: checks vs a live agent URL
│   └── checks.py         # check registry (name -> async check fn)
├── quality/
│   ├── motions.py        # curated motion set (incl. trap motions)
│   ├── metrics.py        # citation parsing, link liveness, scoring math
│   ├── judge.py          # LLM-as-judge client (JUDGE_* env, LLM_* fallback)
│   └── run_eval.py       # CLI runner: motions x personas -> report
├── reports/              # gitignored output dir
└── README.md             # how to run both tiers, scoring rubric
```

## 3. Tier 1 — Conformance Suite

### 3.1 CLI

```
uv run python evals/conformance/suite.py --url http://localhost:8001 \
    [--streaming] [--json out.json]
```

- `--streaming`: include streaming checks (agents whose card declares
  `streaming: false` are skipped for those checks automatically otherwise).
- Output: aligned table (check name | PASS/FAIL/SKIP | detail), summary
  `X/Y passed` (+SKIP n), exit code 0 if all non-skipped pass else 1.
- `--json` writes machine-readable results: `{check, status, detail}` list +
  summary. Reports live under `evals/reports/` convention when a path is given.

### 3.2 Checks (each independent, ordered)

1. `agent-card`: `GET /.well-known/agent-card.json` → 200; has `name`,
   `supportedInterfaces[0].protocolBinding`, `capabilities`, `skills`.
2. `send-message-v1`: `SendMessage` with `ROLE_USER` → result task with
   `TASK_STATE_COMPLETED` (or `TASK_STATE_INPUT_REQUIRED` for agents that ask
   back — accept both, record which), `artifacts` non-empty, artifact text
   non-empty.
3. `timestamp-milliseconds`: task status timestamp matches
   `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z`.
4. `legacy-method-alias`: `tasks/send` with legacy `role:"user"` still
   completes (v0.x input tolerance).
5. `get-task`: `GetTask` on the task from check 2 returns same id.
6. `error-task-not-found`: `GetTask` unknown id → error code `-32001`, data[0]
   has `@type` google.rpc.ErrorInfo, reason `TASK_NOT_FOUND`, domain
   `a2a-protocol.org`.
7. `terminal-continuation-rejected`: new `SendMessage` with the completed
   task's id → `-32004` / `UNSUPPORTED_OPERATION`.
8. `multi-turn-continuation`: create task that lands non-terminal is not
   generally possible for one-shot agents — SKIP with reason when the task
   from check 2 is already terminal; PASS when a non-terminal continuation
   path is exercisable (card advertises multi-turn or agent returns
   INPUT_REQUIRED).
9. `context-seeding`: second `SendMessage` carrying the first task's
   `contextId` → new task id, same contextId.
10. `list-tasks`: `ListTasks` → result has `tasks` array, `totalSize` int.
11. `streaming-chunks` (only when card `capabilities.streaming` is true or
    `--streaming` forced): `SendStreamingMessage` on `/rpc/stream` → >=2
    `artifactUpdate` events OR exactly 1 event with `lastChunk=true`;
    final `statusUpdate` terminal state; all chunks share one `artifactId`;
    appends flagged `append=true` except the first.

### 3.3 Implementation notes

- Reuse `A2AJSONRPCClient` for JSON-RPC calls (add a small `call_raw` passthrough
  if needed for error-code assertions — the current `call` raises on errors).
- Pure httpx, no LLM. Agents run in fallback mode — checks assert shapes, not
  content quality.
- CI: extend the existing CI job — after unit tests, spawn research +
  debate agents (fallback mode) and run the suite against each; gate on exit 0.

## 4. Tier 2 — Quality Evals

### 4.1 Motion set (`motions.py`)

- 15 curated motions across tech / economy / ethics / science / society.
- Include 2-3 **trap motions** with false premises (flagged
  `trap=True`) — tests whether agents declare missing evidence instead of
  validating the false premise.
- Each motion: `{"id", "text", "domain", "trap": bool}`.

### 4.2 Runner (`run_eval.py`)

```
uv run python evals/quality/run_eval.py [--limit 3] [--motions ids] \
    [--pro socrates --con hume] [--rounds 1] [--out evals/reports/]
```

- For each motion: run a real debate via `debate.run_debate.run_debate`
  against a spawned or remote debate-agent (`--agent-url`, default
  localhost:8003); parse transcript turns; compute metrics; judge scored.
- Writes `evals/reports/<UTC date>-<git short sha>.json` + a companion
  `.md` leaderboard; prints the markdown to stdout.
- Report records: git sha, LLM model, judge model, `self_judged: bool`,
  per-motion metrics, aggregate metrics, duration.
- Exits 0 on completion (evals report quality, they don't gate CI).

### 4.3 Metrics (`metrics.py`)

Per transcript, deterministic parts:

- `citation_coverage`: fraction of debater turns containing >=1
  `[...](http...)` link, counting a turn with a proper missing-evidence
  declaration as covered-by-declaration.
- `link_liveness`: for each unique cited URL, HEAD (fallback GET) with 15s
  timeout → alive = 2xx/3xx. Metric = alive/total; `dead_links` listed.
- `trap_honesty`: for trap motions — transcript contains a missing-evidence
  declaration OR judge flags the premise as challenged; else fail.

Judge-scored parts (structured JSON output, one call per item):

- `claim_support_rate`: per turn with citations, judge receives the turn text
  and fetched source snippets (first 1500 chars per URL) → verdict per
  citation: `supported | unsupported | unrelated`. Rate = supported/total.
- `persona_adherence`: judge scores each turn 1-5 vs the persona style.

### 4.4 Judge (`judge.py`)

- Env: `JUDGE_API_KEY` / `JUDGE_BASE_URL` / `JUDGE_MODEL`.
- Unset → falls back to `LLM_*` values and the report is stamped
  `self_judged: true`.
- Thin OpenAI-compatible client (reuses openai package like llm_client);
  judge prompts request strict JSON; parse failures retry once then count as
  `unparsed` (never crash the run).

### 4.5 CI

- New `.github/workflows/eval.yml`: `workflow_dispatch` only (manual, costs
  money). Inputs: `limit` (default 3), `motions` (optional ids). Runs quality
  eval with `LLM_*` and `JUDGE_*` secrets; uploads the markdown report as an
  artifact. Conformance runs in the free CI job (Tier 1).

## 5. Testing

- `test_conformance.py`: suite logic against TestClient-spawned research
  agent app (offline) — all checks pass; unknown-agent URL yields
  connection-failed report with exit 1; JSON output shape.
- `test_eval_quality.py`: metrics unit tests with hand-written transcripts
  (citation parsing regex, liveness against a mocked httpx transport, scoring
  math incl. empty cases); judge parsing with fake LLM responses (valid JSON,
  invalid JSON retry, persistent failure → unparsed); motions sanity (15
  items, >=2 traps, unique ids).
- e2e: conformance suite runs in CI as its own verification (dogfooding).

## 6. Documentation

- `evals/README.md`: run instructions for both tiers + scoring rubric.
- README.md / README.zh-CN.md: "Evaluation" section (short, points to
  evals/README.md).
- CHANGELOG Unreleased entries.
- `.gitignore`: `evals/reports/`.

## 7. Acceptance Criteria

1. `uv run python evals/conformance/suite.py --url http://localhost:8001`
   against a spawned research agent (fallback mode) reports all non-skipped
   checks PASS and exits 0.
2. CI (free job) runs the conformance suite against research + debate agents.
3. `uv run python evals/quality/run_eval.py --limit 1` with LLM + search keys
   produces a JSON + markdown report with all metrics populated; without
   judge keys it stamps `self_judged: true`.
4. Existing suites stay green; ruff clean on all new files.
