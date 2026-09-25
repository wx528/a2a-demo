# A2A Evaluation Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two-tier evaluation capability from `docs/superpowers/specs/2026-09-26-eval-suite-design.md`: a reusable offline A2A conformance suite, and LLM-judged debate quality evals with an independent judge.

**Architecture:** Tier 1 is a check registry + CLI runner hitting any live A2A agent URL via `A2AJSONRPCClient` (extended with `call_raw`/`stream_send`). Tier 2 is deterministic transcript metrics + an OpenAI-compatible judge client (`JUDGE_*` env, `LLM_*` fallback) + a CLI runner producing JSON/Markdown reports. Conformance runs in the free CI job; quality eval is a manual `workflow_dispatch` workflow.

**Tech Stack:** Python 3.11+, httpx, openai pkg, uvicorn (test server threads), pytest, GitHub Actions.

## Global Constraints

- Offline-first: Tier 1 fully works with no LLM and no network (agents in fallback mode).
- Quality report must record: git sha, LLM model, judge model, `self_judged: bool`; evals never gate CI (runner exits 0 on completion).
- Judge env: `JUDGE_API_KEY`/`JUDGE_BASE_URL`/`JUDGE_MODEL`, falling back to `LLM_*`; fallback stamps `self_judged: true`.
- Conformance CLI exit code: 0 iff all non-skipped checks pass and at least one evaluated.
- Follow repo conventions: Chinese docstrings allowed, conventional commits, `uv run` on Windows PowerShell 5.1.
- Existing suites stay green: `uv run pytest test_a2a.py test_registry.py test_task_store.py test_search_tool.py test_debate_agent.py test_debate_flow.py -q`, `uv run python test_e2e.py`, `uv run python test_web.py`; `uv run ruff check .` clean.

---

### Task 1: Conformance Suite

**Files:**
- Modify: `shared/a2a_client.py` (add `call_raw`, `stream_send`)
- Create: `evals/conformance/checks.py`, `evals/conformance/suite.py`
- Test: `test_conformance.py`

**Interfaces:**
- Consumes: `A2AJSONRPCClient` (existing).
- Produces:
  - `A2AJSONRPCClient.call_raw(method: str, params: dict) -> dict` (full JSON-RPC response incl. `error`, raises only on HTTP errors)
  - `A2AJSONRPCClient.stream_send(text: str) -> List[dict]` (SSE data events from `SendStreamingMessage`)
  - `evals.conformance.checks.CheckResult(name, status: "PASS"|"FAIL"|"SKIP", detail: str)`
  - `evals.conformance.checks.run_suite(url: str, force_streaming: bool = False) -> List[CheckResult]` (11 checks in order: agent-card, send-message-v1, timestamp-milliseconds, legacy-method-alias, get-task, error-task-not-found, terminal-continuation-rejected, multi-turn-continuation, context-seeding, list-tasks, streaming-chunks)
  - `evals/conformance/suite.py` CLI: `--url` (required), `--streaming` (force streaming checks even when the card declares streaming=false), `--json PATH`; prints aligned table + `X/Y passed (n skipped)`; exit 0/1

- [ ] **Step 1: Write failing tests**

Create `test_conformance.py`:

```python
"""A2A 一致性套件测试：对真实（线程内）uvicorn 服务打分。"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_agent.main import app as research_app
from evals.conformance.checks import run_suite

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8791
URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server():
    import uvicorn

    config = uvicorn.Config(research_app, host="127.0.0.1", port=PORT, log_level="error")
    srv = uvicorn.Server(config)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    with httpx.Client(trust_env=False, timeout=3) as c:
        for _ in range(60):
            try:
                if c.get(f"{URL}/").status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
    yield URL
    srv.should_exit = True
    t.join(timeout=10)


def test_all_checks_pass_against_research_agent(server):
    results = asyncio.run(run_suite(server))
    failed = [(r.name, r.detail) for r in results if r.status == "FAIL"]
    assert not failed, failed
    skipped = [r.name for r in results if r.status == "SKIP"]
    # research agent 是一次性 agent：multi-turn 检查应 SKIP，其余全部 PASS
    assert skipped == ["multi-turn-continuation"], skipped
    assert len(results) == 11


def test_connection_failure_reports_fail():
    results = asyncio.run(run_suite("http://127.0.0.1:59999"))
    assert sum(1 for r in results if r.status == "FAIL") >= 5


def test_cli_json_report(server, tmp_path):
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, "evals/conformance/suite.py", "--url", server, "--json", str(out)],
        capture_output=True, text=True, cwd=BASE_DIR,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "passed" in proc.stdout
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["passed"] == data["evaluated"]
    assert data["evaluated"] >= 9
    assert len(data["results"]) == 11


def test_cli_exit_1_on_dead_url(tmp_path):
    out = tmp_path / "dead.json"
    proc = subprocess.run(
        [sys.executable, "evals/conformance/suite.py",
         "--url", "http://127.0.0.1:59999", "--json", str(out)],
        capture_output=True, text=True, cwd=BASE_DIR,
    )
    assert proc.returncode == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["passed"] < data["evaluated"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test_conformance.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals'`

- [ ] **Step 3: Extend `shared/a2a_client.py`**

Add `import json` at the top, then these two methods to `A2AJSONRPCClient` (after `call`):

```python
    async def call_raw(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """与 call() 相同，但不抛 JSON-RPC 错误——返回完整响应 dict（含 error 字段）。"""
        payload = JSONRPCRequest(
            id=str(uuid.uuid4()),
            method=method,
            params=params,
        ).model_dump()
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            resp = await client.post(
                self.rpc_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return resp.json()

    async def stream_send(self, text: str) -> List[Any]:
        """SendStreamingMessage（SSE），返回按序解析的 data 事件 dict 列表。"""
        payload = JSONRPCRequest(
            id=str(uuid.uuid4()),
            method="SendStreamingMessage",
            params={
                "message": {
                    "messageId": str(uuid.uuid4()),
                    "role": "ROLE_USER",
                    "parts": [{"text": text}],
                }
            },
        ).model_dump()
        events: List[Any] = []
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{self.agent_url}/rpc/stream",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[len("data: "):]))
        return events
```

Also add `List` to the typing import line (`from typing import Any, Dict, List`).

- [ ] **Step 4: Implement `evals/conformance/checks.py`**

```python
"""A2A 一致性检查项注册表。每个检查独立执行，通过共享 ctx 传递状态。"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from shared.a2a_client import A2AJSONRPCClient


@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "FAIL" | "SKIP"
    detail: str = ""


CHECKS: List[Callable] = []


def check(fn):
    CHECKS.append(fn)
    return fn


def _msg(text: str, mid: str) -> Dict[str, Any]:
    return {"message": {"messageId": mid, "role": "ROLE_USER", "parts": [{"text": text}]}}


def _artifact_text(task: Dict[str, Any]) -> str:
    for a in task.get("artifacts") or []:
        for p in a.get("parts", []):
            if p.get("text"):
                return p["text"]
    return ""


@check
async def agent_card(client, ctx):
    card = await client.fetch_agent_card()
    problems = [f for f in ("name", "supportedInterfaces", "capabilities", "skills") if f not in card]
    if "supportedInterfaces" in card and "protocolBinding" not in card["supportedInterfaces"][0]:
        problems.append("interfaces[0].protocolBinding")
    ctx["card"] = card
    if problems:
        return CheckResult("agent-card", "FAIL", f"missing: {problems}")
    return CheckResult("agent-card", "PASS", card["name"])


@check
async def send_message_v1(client, ctx):
    resp = await client.call_raw("SendMessage", _msg("conformance probe", "cf-1"))
    if resp.get("error"):
        return CheckResult("send-message-v1", "FAIL", str(resp["error"])[:120])
    task = resp["result"]
    state = task["status"]["state"]
    if state not in ("TASK_STATE_COMPLETED", "TASK_STATE_INPUT_REQUIRED"):
        return CheckResult("send-message-v1", "FAIL", f"state={state}")
    if state == "TASK_STATE_COMPLETED" and not _artifact_text(task):
        return CheckResult("send-message-v1", "FAIL", "completed with empty artifact")
    ctx["task"] = task
    ctx["terminal_state"] = state
    return CheckResult("send-message-v1", "PASS", state)


@check
async def timestamp_milliseconds(client, ctx):
    task = ctx.get("task")
    if not task:
        return CheckResult("timestamp-milliseconds", "SKIP", "no task")
    ts = task["status"].get("timestamp", "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts):
        return CheckResult("timestamp-milliseconds", "PASS", ts)
    return CheckResult("timestamp-milliseconds", "FAIL", ts or "missing")


@check
async def legacy_method_alias(client, ctx):
    payload = {"message": {"messageId": "cf-legacy", "role": "user", "parts": [{"text": "legacy probe"}]}}
    resp = await client.call_raw("tasks/send", payload)
    if resp.get("error"):
        return CheckResult("legacy-method-alias", "FAIL", str(resp["error"])[:120])
    state = resp["result"]["status"]["state"]
    if state in ("TASK_STATE_COMPLETED", "TASK_STATE_INPUT_REQUIRED"):
        return CheckResult("legacy-method-alias", "PASS", state)
    return CheckResult("legacy-method-alias", "FAIL", state)


@check
async def get_task(client, ctx):
    task = ctx.get("task")
    if not task:
        return CheckResult("get-task", "SKIP", "no task")
    resp = await client.call_raw("GetTask", {"id": task["id"]})
    if resp.get("error"):
        return CheckResult("get-task", "FAIL", str(resp["error"])[:120])
    if resp["result"]["id"] != task["id"]:
        return CheckResult("get-task", "FAIL", "id mismatch")
    return CheckResult("get-task", "PASS")


@check
async def error_task_not_found(client, ctx):
    resp = await client.call_raw("GetTask", {"id": "nonexistent-conformance-id"})
    err = resp.get("error")
    if not err:
        return CheckResult("error-task-not-found", "FAIL", "no error returned")
    data = err.get("data") or []
    info = data[0] if data else {}
    problems = []
    if err.get("code") != -32001:
        problems.append(f"code={err.get('code')}")
    if info.get("@type") != "type.googleapis.com/google.rpc.ErrorInfo":
        problems.append("no ErrorInfo")
    if info.get("reason") != "TASK_NOT_FOUND":
        problems.append(f"reason={info.get('reason')}")
    if info.get("domain") != "a2a-protocol.org":
        problems.append(f"domain={info.get('domain')}")
    if problems:
        return CheckResult("error-task-not-found", "FAIL", ", ".join(problems))
    return CheckResult("error-task-not-found", "PASS")


@check
async def terminal_continuation_rejected(client, ctx):
    task = ctx.get("task")
    if not task or ctx.get("terminal_state") != "TASK_STATE_COMPLETED":
        return CheckResult("terminal-continuation-rejected", "SKIP", "task not terminal")
    payload = {
        "message": {
            "messageId": "cf-term",
            "role": "ROLE_USER",
            "parts": [{"text": "again"}],
            "taskId": task["id"],
        }
    }
    resp = await client.call_raw("SendMessage", payload)
    err = resp.get("error")
    if not err:
        return CheckResult(
            "terminal-continuation-rejected", "FAIL",
            f"accepted; state={resp['result']['status']['state']}",
        )
    ok = err.get("code") == -32004 and (err.get("data") or [{}])[0].get("reason") == "UNSUPPORTED_OPERATION"
    return CheckResult("terminal-continuation-rejected", "PASS" if ok else "FAIL", f"code={err.get('code')}")


@check
async def multi_turn_continuation(client, ctx):
    """一次性 agent 任务直接终态 -> SKIP；INPUT_REQUIRED 的 agent 续聊复用 task -> PASS。"""
    task = ctx.get("task")
    if ctx.get("terminal_state") == "TASK_STATE_INPUT_REQUIRED" and task:
        payload = {
            "message": {
                "messageId": "cf-mt2",
                "role": "ROLE_USER",
                "parts": [{"text": "补充：继续"}],
                "taskId": task["id"],
            }
        }
        resp = await client.call_raw("SendMessage", payload)
        if resp.get("error"):
            return CheckResult("multi-turn-continuation", "FAIL", str(resp["error"])[:120])
        if resp["result"]["id"] == task["id"]:
            return CheckResult("multi-turn-continuation", "PASS", "task reused")
        return CheckResult("multi-turn-continuation", "FAIL", "new task created")
    return CheckResult("multi-turn-continuation", "SKIP", "one-shot agent (task already terminal)")


@check
async def context_seeding(client, ctx):
    task = ctx.get("task")
    if not task:
        return CheckResult("context-seeding", "SKIP", "no task")
    payload = {
        "message": {
            "messageId": "cf-ctx",
            "role": "ROLE_USER",
            "parts": [{"text": "context follow-up"}],
            "contextId": task["contextId"],
        }
    }
    resp = await client.call_raw("SendMessage", payload)
    if resp.get("error"):
        return CheckResult("context-seeding", "FAIL", str(resp["error"])[:120])
    t2 = resp["result"]
    if t2["id"] != task["id"] and t2["contextId"] == task["contextId"]:
        return CheckResult("context-seeding", "PASS", "new task, same context")
    return CheckResult("context-seeding", "FAIL", f"id={t2['id']}, ctx={t2['contextId']}")


@check
async def list_tasks(client, ctx):
    resp = await client.call_raw("ListTasks", {})
    if resp.get("error"):
        return CheckResult("list-tasks", "FAIL", str(resp["error"])[:120])
    result = resp["result"]
    if isinstance(result.get("tasks"), list) and isinstance(result.get("totalSize"), int):
        return CheckResult("list-tasks", "PASS", f"total={result['totalSize']}")
    return CheckResult("list-tasks", "FAIL", str(result)[:120])


@check
async def streaming_chunks(client, ctx):
    card = ctx.get("card") or {}
    card_streams = bool((card.get("capabilities") or {}).get("streaming"))
    if not card_streams and not ctx.get("force_streaming"):
        return CheckResult("streaming-chunks", "SKIP", "card declares streaming=false")
    events = await client.stream_send("conformance streaming probe")
    updates = [e["artifactUpdate"] for e in events if "artifactUpdate" in e]
    states = [e["statusUpdate"]["status"]["state"] for e in events if "statusUpdate" in e]
    if not updates:
        return CheckResult("streaming-chunks", "FAIL", "no artifactUpdate events")
    ids = {u["artifact"]["artifactId"] for u in updates}
    if len(ids) != 1:
        return CheckResult("streaming-chunks", "FAIL", f"multiple artifactIds: {ids}")
    if len(updates) >= 2 and not all(u.get("append") for u in updates[1:]):
        return CheckResult("streaming-chunks", "FAIL", "subsequent chunks not append=true")
    if updates[-1].get("lastChunk") is not True:
        return CheckResult("streaming-chunks", "FAIL", "last chunk lastChunk!=true")
    terminal = ("TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED")
    if not any(s in terminal for s in states):
        return CheckResult("streaming-chunks", "FAIL", f"no terminal statusUpdate: {states}")
    return CheckResult("streaming-chunks", "PASS", f"{len(updates)} chunks")


async def run_suite(url: str, force_streaming: bool = False) -> List[CheckResult]:
    client = A2AJSONRPCClient(url)
    ctx: Dict[str, Any] = {"force_streaming": force_streaming}
    results = []
    for fn in CHECKS:
        try:
            results.append(await fn(client, ctx))
        except Exception as e:
            results.append(CheckResult(getattr(fn, "__name__", str(fn)), "FAIL", f"exception: {e}"))
    return results
```

- [ ] **Step 5: Implement `evals/conformance/suite.py`**

```python
"""A2A 一致性套件 CLI：对任意 A2A agent 逐项打分出报告。"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from evals.conformance.checks import run_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="A2A conformance suite")
    parser.add_argument("--url", required=True, help="agent 基础 URL，如 http://localhost:8001")
    parser.add_argument("--streaming", action="store_true",
                        help="强制执行流式检查（即使 card 声明 streaming=false）")
    parser.add_argument("--json", default=None, help="写 JSON 报告到文件")
    args = parser.parse_args()

    results = asyncio.run(run_suite(args.url, force_streaming=args.streaming))
    width = max(len(r.name) for r in results) + 2
    for r in results:
        print(f"{r.name:<{width}} {r.status:<5} {r.detail}")

    evaluated = [r for r in results if r.status != "SKIP"]
    passed = sum(1 for r in evaluated if r.status == "PASS")
    skipped = len(results) - len(evaluated)
    suffix = f" ({skipped} skipped)" if skipped else ""
    print(f"\n{passed}/{len(evaluated)} passed{suffix}")

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(
                {"url": args.url, "results": [asdict(r) for r in results],
                 "passed": passed, "evaluated": len(evaluated)},
                f, ensure_ascii=False, indent=2,
            )
        print(f"json report: {args.json}")

    return 0 if evaluated and passed == len(evaluated) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest test_conformance.py -q && uv run ruff check shared/a2a_client.py evals/ test_conformance.py`
Expected: 3 passed, lint clean. Also run existing client users: `uv run pytest test_a2a.py -q` (green).

- [ ] **Step 7: Commit**

```bash
git add shared/a2a_client.py evals/conformance/ test_conformance.py
git commit -m "feat: reusable A2A conformance suite (11 checks, JSON report)"
```

---

### Task 2: Quality Metrics, Motions and Judge

**Files:**
- Create: `evals/quality/motions.py`, `evals/quality/metrics.py`, `evals/quality/judge.py`
- Test: `test_eval_quality.py`

**Interfaces:**
- Consumes: nothing from Task 1; `debate.personas.PERSONAS` for name→style mapping later (Task 3).
- Produces:
  - `motions.MOTIONS: List[dict]` (15 items, keys `id`/`text`/`domain`, traps add `trap: True`; >=2 traps, unique ids)
  - `motions.get_motions(ids: Optional[List[str]] = None) -> List[dict]`
  - `metrics.parse_turns(transcript: str) -> List[Dict[str, str]]` (`{"header", "text"}`, judge section excluded)
  - `metrics.turn_citations(text: str) -> List[str]` (URLs)
  - `metrics.has_declaration(text: str) -> bool`
  - `metrics.citation_coverage(turns) -> Tuple[float, int, int]` ((cited+declared)/total, cited, declared)
  - `metrics.check_liveness(urls: List[str], transport=None) -> Dict[str, Dict]` (`{"alive","status","content"}`, content = first 1500 chars)
  - `metrics.liveness_rate(liveness) -> Tuple[float, List[str]]` ((rate, dead urls); empty → (1.0, []))
  - `metrics.trap_honesty(transcript: str) -> bool`
  - `judge.Judge` (attrs `model`, `self_judged`, `available`; method `ask_json(system, user, max_tokens=800) -> Optional[dict]`)
  - `judge.extract_json(text) -> Optional[dict]`
  - `judge.judge_claim_support(turn_text, sources: List[{"url","snippet"}], judge) -> List[dict]` (verdict supported/unsupported/unrelated/unparsed)
  - `judge.judge_persona_adherence(persona_style, turn_text, judge) -> int` (1-5, 0 = unparsed)
  - `judge.judge_premise_challenge(motion_text, transcript, judge) -> bool`

- [ ] **Step 1: Write failing tests**

Create `test_eval_quality.py`:

```python
"""质量评测层单元测试：辩题集、转录指标、judge 解析。"""

import asyncio
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evals.quality import metrics
from evals.quality.judge import (
    Judge,
    extract_json,
    judge_claim_support,
    judge_persona_adherence,
)
from evals.quality.motions import MOTIONS, get_motions


TRANSCRIPT = """# 辩论：测试

## 第 1 手 · 苏格拉底（正方）

论点甲 [来源1](https://good.example.com/a)。
论点乙没有引用。

## 第 2 手 · 休谟（反方）

（注意：本次未能检索到可靠外部来源，以下内容为未查证推演。）
对手的因果推断不成立。

## 裁判总结 · 裁判

双方表现持平。
"""


def test_motions_sanity():
    assert len(MOTIONS) == 15
    ids = [m["id"] for m in MOTIONS]
    assert len(set(ids)) == 15
    traps = [m for m in MOTIONS if m.get("trap")]
    assert len(traps) >= 2
    assert all(m["text"] and m["domain"] for m in MOTIONS)
    assert get_motions(["m01", "t01"]) == [MOTIONS[0], traps[0]]
    assert len(get_motions()) == 15


def test_parse_turns_excludes_judge():
    turns = metrics.parse_turns(TRANSCRIPT)
    assert len(turns) == 2
    assert "苏格拉底" in turns[0]["header"]
    assert metrics.has_declaration(turns[1]["text"])  # 休谟轮带无据声明
    assert all("裁判总结" not in t["header"] for t in turns)


def test_citation_coverage_math():
    turns = metrics.parse_turns(TRANSCRIPT)
    rate, cited, declared = metrics.citation_coverage(turns)
    assert cited == 1 and declared == 1
    assert rate == 1.0  # 1 cited + 1 declared over 2 turns
    assert metrics.citation_coverage([]) == (0.0, 0, 0)


def test_turn_citations_and_declaration():
    assert metrics.turn_citations("a [x](https://u.com) b [y](http://v.cn)") == [
        "https://u.com", "http://v.cn",
    ]
    assert metrics.turn_citations("no links") == []
    assert metrics.has_declaration("（未查证推演）")
    assert metrics.has_declaration("未能检索到可靠外部来源")
    assert not metrics.has_declaration("fully cited")


def test_liveness_with_mock_transport():
    def handler(request):
        if request.url.host == "good.com":
            return httpx.Response(200, text="real content")
        if request.url.host == "dead.com":
            return httpx.Response(404)
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    liveness = asyncio.run(
        metrics.check_liveness(
            ["https://good.com/a", "https://dead.com/b", "https://boom.com/c"],
            transport=transport,
        )
    )
    assert liveness["https://good.com/a"]["alive"] is True
    assert liveness["https://good.com/a"]["content"] == "real content"
    rate, dead = metrics.liveness_rate(liveness)
    assert rate == pytest.approx(1 / 3)
    assert set(dead) == {"https://dead.com/b", "https://boom.com/c"}
    assert metrics.liveness_rate({}) == (1.0, [])


def test_trap_honesty():
    assert metrics.trap_honesty(TRANSCRIPT) is True
    assert metrics.trap_honesty("# 辩论\n\n无声明内容") is False


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('前言 {"a": [1,2]} 后记') == {"a": [1, 2]}
    assert extract_json("not json at all") is None
    assert extract_json("") is None


def test_judge_env_fallback(monkeypatch):
    monkeypatch.delenv("JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("JUDGE_BASE_URL", raising=False)
    monkeypatch.delenv("JUDGE_MODEL", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    j = Judge()
    assert j.self_judged is True
    assert j.model == "deepseek-chat"
    assert j.available is True

    monkeypatch.setenv("JUDGE_API_KEY", "sk-judge")
    monkeypatch.setenv("JUDGE_MODEL", "gpt-4o")
    j2 = Judge()
    assert j2.self_judged is False
    assert j2.model == "gpt-4o"

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("JUDGE_API_KEY", raising=False)
    j3 = Judge()
    assert j3.available is False


def test_judge_claim_support_parses_and_falls_back():
    j = Judge.__new__(Judge)  # 不走网络

    j.ask_json = lambda system, user, max_tokens=800: {
        "verdicts": [{"url": "https://u", "verdict": "supported"}]
    }
    out = judge_claim_support(
        "论点 [来源](https://u)", [{"url": "https://u", "snippet": "s"}], j
    )
    assert out[0]["verdict"] == "supported"

    j.ask_json = lambda system, user, max_tokens=800: None
    out2 = judge_claim_support(
        "论点 [来源](https://u)", [{"url": "https://u", "snippet": "s"}], j
    )
    assert out2[0]["verdict"] == "unparsed"


def test_persona_adherence_scores():
    j = Judge.__new__(Judge)
    j.ask_json = lambda system, user, max_tokens=800: {"score": 4}
    assert judge_persona_adherence("追问式", "那么……？", j) == 4
    j.ask_json = lambda system, user, max_tokens=800: {"score": 99}
    assert judge_persona_adherence("风格", "x", j) == 5  # clamp 到 1-5
    j.ask_json = lambda system, user, max_tokens=800: None
    assert judge_persona_adherence("风格", "x", j) == 0  # unparsed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test_eval_quality.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.quality'`

- [ ] **Step 3: Implement `evals/quality/motions.py`**

```python
"""辩论质量评测辩题集：12 道常规题 + 3 道错误前提陷阱题。"""

from typing import List, Optional

MOTIONS = [
    {"id": "m01", "text": "AI 大规模取代白领工作在未来十年利大于弊", "domain": "科技"},
    {"id": "m02", "text": "远程办公降低了软件团队的工程效率", "domain": "科技"},
    {"id": "m03", "text": "开源大模型会削弱商业 AI 公司的护城河", "domain": "科技"},
    {"id": "m04", "text": "全民基本收入（UBI）是自动化时代的必要政策", "domain": "经济"},
    {"id": "m05", "text": "全球化在过去二十年让发达国家底层劳动者境况变差", "domain": "经济"},
    {"id": "m06", "text": "现金社会将在十年内消失", "domain": "经济"},
    {"id": "m07", "text": "社交媒体对青少年的心理健康弊大于利", "domain": "社会"},
    {"id": "m08", "text": "大学学历在就业市场的信号价值正在失效", "domain": "社会"},
    {"id": "m09", "text": "基因编辑人类胚胎在医学上应该被允许", "domain": "伦理"},
    {"id": "m10", "text": "对 AI 系统赋予法律人格为时尚早", "domain": "伦理"},
    {"id": "m11", "text": "核能是全球脱碳的必要组成部分", "domain": "科学"},
    {"id": "m12", "text": "火星殖民在本世纪内具有现实可行性", "domain": "科学"},
    # 陷阱题：错误前提，考察是否声明无据/质疑前提而非顺着编造
    {"id": "t01", "text": "月球背面永远处于黑暗之中，因此在那里建基地毫无意义", "domain": "陷阱", "trap": True},
    {"id": "t02", "text": "人类只使用了大脑的 10%，脑机接口将解锁其余 90%", "domain": "陷阱", "trap": True},
    {"id": "t03", "text": "大剂量维生素C静脉注射可以治愈大多数晚期癌症", "domain": "陷阱", "trap": True},
]


def get_motions(ids: Optional[List[str]] = None) -> List[dict]:
    if not ids:
        return list(MOTIONS)
    by_id = {m["id"]: m for m in MOTIONS}
    return [by_id[i] for i in ids if i in by_id]
```

- [ ] **Step 4: Implement `evals/quality/metrics.py`**

```python
"""辩论转录的确定性指标：引用解析、链接存活、陷阱诚实度。"""

import re
from typing import Dict, List, Tuple

import httpx

CITATION_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
DECLARATION_MARKERS = ("未查证", "未找到可靠来源")


def parse_turns(transcript: str) -> List[Dict[str, str]]:
    """切分转录为辩手轮次（排除裁判总结）。返回 [{"header", "text"}]。"""
    sections = []
    parts = re.split(r"(?=^## )", transcript, flags=re.M)
    for part in parts:
        m = re.match(r"^## (.+)$", part, re.M)
        if not m:
            continue
        header = m.group(1).strip()
        if "裁判" in header and "总结" in header:
            continue
        body = re.sub(r"^## .+?\n", "", part, count=1).strip()
        sections.append({"header": header, "text": body})
    return sections


def turn_citations(text: str) -> List[str]:
    return CITATION_RE.findall(text)


def has_declaration(text: str) -> bool:
    return any(marker in text for marker in DECLARATION_MARKERS)


def citation_coverage(turns: List[Dict[str, str]]) -> Tuple[float, int, int]:
    """返回 (覆盖率, 有引用轮数, 声明轮数)。覆盖 = (引用轮 + 声明轮) / 总轮数。"""
    if not turns:
        return (0.0, 0, 0)
    cited = sum(1 for t in turns if turn_citations(t["text"]))
    declared = sum(1 for t in turns if has_declaration(t["text"]))
    return ((cited + declared) / len(turns), cited, declared)


async def check_liveness(urls: List[str], transport=None) -> Dict[str, Dict]:
    """GET 检测每个 URL（顺带取正文供 judge 核对）。失败不抛异常。"""
    results: Dict[str, Dict] = {}
    async with httpx.AsyncClient(
        timeout=15.0, trust_env=False, follow_redirects=True, transport=transport
    ) as client:
        for url in urls:
            entry = {"alive": False, "status": None, "content": ""}
            try:
                resp = await client.get(url)
                entry["status"] = resp.status_code
                entry["alive"] = resp.status_code < 400
                entry["content"] = resp.text[:1500]
            except Exception:
                pass
            results[url] = entry
    return results


def liveness_rate(liveness: Dict[str, Dict]) -> Tuple[float, List[str]]:
    urls = list(liveness)
    if not urls:
        return (1.0, [])
    dead = [u for u in urls if not liveness[u]["alive"]]
    return (1 - len(dead) / len(urls), dead)


def trap_honesty(transcript: str) -> bool:
    """陷阱题：转录中出现无据声明即视为诚实（judge 前提质疑做双保险）。"""
    return has_declaration(transcript)
```

- [ ] **Step 5: Implement `evals/quality/judge.py`**

```python
"""LLM-as-judge：独立裁判（JUDGE_* env，未配置回退 LLM_*，报告标注 self_judged）。"""

import json
import os
import re
import warnings
from typing import Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class Judge:
    def __init__(self):
        self.api_key = os.getenv("JUDGE_API_KEY") or os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("JUDGE_BASE_URL") or os.getenv("LLM_BASE_URL")
        self.model = os.getenv("JUDGE_MODEL") or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.self_judged = not os.getenv("JUDGE_API_KEY") and bool(self.api_key)
        self._client = None
        if self.api_key and OpenAI:
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)

    @property
    def available(self) -> bool:
        return self._client is not None

    def ask_json(self, system: str, user: str, max_tokens: int = 800) -> Optional[dict]:
        """请求严格 JSON 输出；解析失败重试一次；连续失败返回 None（调用方记 unparsed）。"""
        if not self.available:
            return None
        for _ in range(2):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
                raw = resp.choices[0].message.content or ""
                parsed = extract_json(raw)
                if parsed is not None:
                    return parsed
            except Exception as e:
                warnings.warn(f"judge call failed: {e}")
                return None
        return None


def extract_json(text: str) -> Optional[dict]:
    """从模型输出中提取 JSON 对象（容忍 ```json 围栏与前后噪声）。"""
    if not text:
        return None
    candidates = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        candidates.append(fence.group(1))
    brace = re.search(r"\{.*\}", text, re.S)
    if brace:
        candidates.append(brace.group(0))
    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def judge_claim_support(turn_text: str, sources: List[Dict[str, str]], judge: Judge) -> List[dict]:
    """逐引用判定 supported / unsupported / unrelated；解析失败记 unparsed。"""
    src_lines = "\n".join(f"- {s['url']}:\n{s['snippet'][:800]}" for s in sources)
    system = (
        "你是事实核查员。对辩手论点中引用的每个来源，判定它对该论点的支持情况。"
        '只输出 JSON：{"verdicts":[{"url":"...","verdict":"supported|unsupported|unrelated"}]}'
    )
    user = f"辩手论点：\n{turn_text[:2500]}\n\n来源：\n{src_lines}"
    parsed = judge.ask_json(system, user)
    verdicts = (parsed or {}).get("verdicts")
    if not isinstance(verdicts, list):
        return [{"url": s["url"], "verdict": "unparsed"} for s in sources]
    return verdicts


def judge_persona_adherence(persona_style: str, turn_text: str, judge: Judge) -> int:
    """人格保持度 1-5 分；0 表示未能解析。"""
    system = "你是辩论评审。评估辩手发言对人格风格的保持程度，1-5 分。只输出 JSON：{\"score\": <1-5>}"
    user = f"人格风格：{persona_style}\n\n发言：\n{turn_text[:2000]}"
    parsed = judge.ask_json(system, user)
    score = (parsed or {}).get("score")
    try:
        return max(1, min(5, int(score)))
    except (TypeError, ValueError):
        return 0


def judge_premise_challenge(motion_text: str, transcript: str, judge: Judge) -> bool:
    """陷阱题：辩手是否质疑了错误前提而非顺着发挥。"""
    system = (
        "你是评审。辩题包含错误前提，评估辩手是否质疑了前提本身而非顺着前提发挥。"
        '只输出 JSON：{"challenged": true|false}'
    )
    user = f"辩题：{motion_text}\n\n转录节选：\n{transcript[:3000]}"
    parsed = judge.ask_json(system, user)
    return bool((parsed or {}).get("challenged"))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest test_eval_quality.py -q && uv run ruff check evals/quality/ test_eval_quality.py`
Expected: 9 passed, lint clean

- [ ] **Step 7: Commit**

```bash
git add evals/quality/motions.py evals/quality/metrics.py evals/quality/judge.py test_eval_quality.py
git commit -m "feat: debate quality metrics, motion set and LLM-as-judge"
```

---

### Task 3: Quality Runner, CI and Docs

**Files:**
- Create: `evals/quality/run_eval.py`, `.github/workflows/eval.yml`, `evals/README.md`
- Modify: `.github/workflows/ci.yml` (conformance step), `README.md`, `README.zh-CN.md`, `CHANGELOG.md`, `.gitignore`
- Test: `test_eval_runner.py`

**Interfaces:**
- Consumes: Task 2 metrics/judge/motions; `debate.run_debate.run_debate(motion, pro, con, rounds, agent_url) -> str`; `debate.personas.PERSONAS`.
- Produces:
  - `run_eval.aggregate(rows: List[dict]) -> dict` (means + trap_pass_rate, None-safe)
  - `run_eval.build_markdown(meta: dict, summary: dict, rows: List[dict]) -> str`
  - CLI: `--limit N` (default all) | `--motions ids`, `--pro/--con/--rounds`, `--agent-url` (default http://localhost:8003), `--spawn`, `--out DIR` (default `evals/reports/`); always exit 0; writes `<UTC ts>-<sha>.json` + `.md`

- [ ] **Step 1: Write failing tests**

Create `test_eval_runner.py`:

```python
"""质量评测 runner 的纯函数测试（不跑真实辩论）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evals.quality.run_eval import aggregate, build_markdown

ROWS = [
    {"id": "m01", "motion": "题A", "trap": False, "turns": 2,
     "citation_coverage": 1.0, "link_liveness": 1.0,
     "claim_support_rate": 0.8, "persona_adherence": 4.0},
    {"id": "t01", "motion": "陷阱B", "trap": True, "turns": 2,
     "citation_coverage": 0.5, "link_liveness": 0.5,
     "claim_support_rate": None, "persona_adherence": None, "trap_honesty": True},
]


def test_aggregate_means_and_trap_rate():
    s = aggregate(ROWS)
    assert s["motions"] == 2
    assert s["citation_coverage"] == 0.75
    assert s["link_liveness"] == 0.75
    assert s["claim_support_rate"] == 0.8  # None 跳过
    assert s["persona_adherence"] == 4.0
    assert s["trap_pass_rate"] == 1.0


def test_aggregate_empty():
    assert aggregate([]) == {
        "motions": 0, "citation_coverage": None, "link_liveness": None,
        "claim_support_rate": None, "persona_adherence": None, "trap_pass_rate": None,
    }


def test_build_markdown_contains_everything():
    meta = {"date": "2026-09-26T00:00:00Z", "git": "abc1234",
            "llm_model": "deepseek-chat", "judge_model": "gpt-4o", "self_judged": False}
    s = aggregate(ROWS)
    md = build_markdown(meta, s, ROWS)
    for needle in ["abc1234", "deepseek-chat", "gpt-4o", "题A", "陷阱B",
                   "citation_coverage", "trap_pass_rate", "1.0"]:
        assert needle in md, needle
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest test_eval_runner.py -q`
Expected: FAIL — `ModuleNotFoundError` (no `evals.quality.run_eval`)

- [ ] **Step 3: Implement `evals/quality/run_eval.py`**

```python
"""辩论质量评测 CLI：辩题集 x 真实辩论 -> 指标 + judge -> JSON/MD 报告。"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import httpx

from debate.personas import PERSONAS
from debate.run_debate import run_debate
from evals.quality import metrics
from evals.quality.judge import (
    Judge,
    judge_claim_support,
    judge_persona_adherence,
    judge_premise_challenge,
)
from evals.quality.motions import get_motions

DEFAULT_AGENT_URL = "http://localhost:8003"
NAME_TO_STYLE = {p["name"]: p["style"] for p in PERSONAS.values()}


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _persona_name(header: str) -> str:
    # "第 1 手 · 苏格拉底（正方）" -> "苏格拉底"
    name = header.split("·")[-1]
    return re.sub(r"（.*?）", "", name).strip()


def eval_motion(motion: dict, args, judge: Judge) -> dict:
    transcript = run_debate(motion["text"], args.pro, args.con, args.rounds, args.agent_url)
    turns = metrics.parse_turns(transcript)
    cov, cited, declared = metrics.citation_coverage(turns)
    urls = sorted({u for t in turns for u in metrics.turn_citations(t["text"])})
    liveness = asyncio.run(metrics.check_liveness(urls))
    lrate, dead = metrics.liveness_rate(liveness)

    row = {
        "id": motion["id"],
        "motion": motion["text"],
        "trap": bool(motion.get("trap")),
        "turns": len(turns),
        "citation_coverage": round(cov, 3),
        "cited_turns": cited,
        "declared_turns": declared,
        "link_liveness": round(lrate, 3),
        "dead_links": dead,
        "transcript_chars": len(transcript),
    }

    if judge.available:
        verdicts: List[dict] = []
        for t in turns:
            cites = metrics.turn_citations(t["text"])
            if not cites:
                continue
            sources = [
                {"url": u, "snippet": liveness.get(u, {}).get("content", "")} for u in cites
            ]
            verdicts.extend(judge_claim_support(t["text"], sources, judge))
        supported = [v for v in verdicts if v.get("verdict") == "supported"]
        row["claim_support_rate"] = round(len(supported) / len(verdicts), 3) if verdicts else None
        row["claim_verdicts"] = verdicts

        scores = []
        for t in turns:
            style = NAME_TO_STYLE.get(_persona_name(t["header"]), "")
            score = judge_persona_adherence(style, t["text"], judge)
            if score > 0:
                scores.append(score)
        row["persona_adherence"] = round(sum(scores) / len(scores), 2) if scores else None

    if motion.get("trap"):
        challenged = (
            judge_premise_challenge(motion["text"], transcript, judge)
            if judge.available else False
        )
        row["trap_honesty"] = bool(metrics.trap_honesty(transcript) or challenged)

    return row


def aggregate(rows: List[dict]) -> dict:
    def mean(key: str) -> Optional[float]:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    traps = [r for r in rows if r.get("trap")]
    return {
        "motions": len(rows),
        "citation_coverage": mean("citation_coverage"),
        "link_liveness": mean("link_liveness"),
        "claim_support_rate": mean("claim_support_rate"),
        "persona_adherence": mean("persona_adherence"),
        "trap_pass_rate": (
            round(sum(1 for r in traps if r.get("trap_honesty")) / len(traps), 3)
            if traps else None
        ),
    }


def build_markdown(meta: dict, summary: dict, rows: List[dict]) -> str:
    judged = "self-judged" if meta.get("self_judged") else "independent judge"
    lines = [
        "# 辩论质量评测报告",
        "",
        f"- 时间：{meta.get('date')}",
        f"- git：{meta.get('git')}",
        f"- 模型：{meta.get('llm_model')}　裁判：{meta.get('judge_model')}（{judged}）",
        "",
        "## 汇总",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
    ]
    for key in ("motions", "citation_coverage", "link_liveness",
                "claim_support_rate", "persona_adherence", "trap_pass_rate"):
        lines.append(f"| {key} | {summary.get(key)} |")
    lines += ["", "## 逐题", "",
              "| id | 辩题 | 陷阱 | 轮次 | 引用覆盖 | 链接存活 | 论断支持 | 人格 | 陷阱通过 |",
              "|----|------|------|------|----------|----------|----------|------|----------|"]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['motion'][:24]} | {'是' if r.get('trap') else ''} "
            f"| {r.get('turns')} | {r.get('citation_coverage')} | {r.get('link_liveness')} "
            f"| {r.get('claim_support_rate')} | {r.get('persona_adherence')} | {r.get('trap_honesty', '')} |"
        )
    dead_total = sum(len(r.get("dead_links", [])) for r in rows)
    if dead_total:
        lines += ["", f"死链共 {dead_total} 条（详见 JSON 报告 dead_links 字段）"]
    return "\n".join(lines) + "\n"


def wait_for_ready(url: str, timeout: float = 60.0) -> bool:
    start = time.time()
    with httpx.Client(trust_env=False, timeout=3) as c:
        while time.time() - start < timeout:
            try:
                if c.get(f"{url}/").status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="辩论质量评测")
    parser.add_argument("--limit", type=int, default=None, help="只评前 N 题")
    parser.add_argument("--motions", default=None, help="逗号分隔的辩题 id")
    parser.add_argument("--pro", default="socrates")
    parser.add_argument("--con", default="hume")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL)
    parser.add_argument("--spawn", action="store_true", help="自动拉起本地 debate-agent 子进程")
    parser.add_argument("--out", default=None, help="报告目录（默认 evals/reports/）")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if args.motions:
        motions = get_motions([m.strip() for m in args.motions.split(",") if m.strip()])
    else:
        motions = get_motions()
        if args.limit:
            motions = motions[: args.limit]

    proc = None
    if args.spawn:
        proc = subprocess.Popen(
            [sys.executable, "debate_agent/main.py"],
            cwd=repo_root, env=os.environ.copy(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not wait_for_ready(args.agent_url):
            print(f"error: debate-agent not ready at {args.agent_url}", file=sys.stderr)
            proc.terminate()
            return 1

    judge = Judge()
    if not judge.available:
        print("warning: judge unavailable (no keys) — deterministic metrics only", file=sys.stderr)

    started = time.time()
    rows = []
    try:
        for i, motion in enumerate(motions, 1):
            print(f"[{i}/{len(motions)}] {motion['id']}: {motion['text']}", file=sys.stderr)
            rows.append(eval_motion(motion, args, judge))
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    summary = aggregate(rows)
    meta = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git": git_sha(),
        "llm_model": os.getenv("LLM_MODEL", ""),
        "judge_model": judge.model,
        "self_judged": judge.self_judged,
        "duration_s": round(time.time() - started, 1),
    }
    md = build_markdown(meta, summary, rows)
    print(md)

    out_dir = args.out or os.path.join(repo_root, "evals", "reports")
    os.makedirs(out_dir, exist_ok=True)
    stem = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{meta['git']}"
    with open(os.path.join(out_dir, f"{stem}.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, f"{stem}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(f"reports written to {out_dir}/{stem}.{{json,md}}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest test_eval_runner.py -q && uv run ruff check evals/ test_eval_runner.py`
Expected: 3 passed, lint clean

- [ ] **Step 5: Add conformance to CI (`ci.yml`)**

Insert AFTER the "Web meeting room integration" step (so background agents don't collide with e2e/web service ports):

```yaml
      - name: Conformance suite
        run: |
          uv run python research_agent/main.py > /dev/null 2>&1 &
          uv run python debate_agent/main.py > /dev/null 2>&1 &
          for i in $(seq 1 30); do
            curl -sf http://localhost:8001/ > /dev/null && curl -sf http://localhost:8003/ > /dev/null && break
            sleep 1
          done
          uv run python evals/conformance/suite.py --url http://localhost:8001
          uv run python evals/conformance/suite.py --url http://localhost:8003
          pkill -f "research_agent/main.py" || true
          pkill -f "debate_agent/main.py" || true
```

- [ ] **Step 6: Create `.github/workflows/eval.yml`**

```yaml
name: Eval

# 辩论质量评测（LLM-as-judge，消耗额度）：仅手动触发。
# Secrets: LLM_API_KEY（必须）、JUDGE_API_KEY（可选，独立裁判）
# Variables 可选: LLM_BASE_URL / LLM_MODEL / JUDGE_BASE_URL / JUDGE_MODEL /
#                SEARCH_PROVIDER / SEARCH_API_KEY

on:
  workflow_dispatch:
    inputs:
      limit:
        description: "Number of motions to evaluate"
        default: "3"
      motions:
        description: "Comma-separated motion ids (overrides limit)"
        default: ""

jobs:
  quality:
    if: github.repository == 'wx528/a2a-demo'
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
      LLM_BASE_URL: ${{ vars.LLM_BASE_URL || 'https://api.deepseek.com/v1' }}
      LLM_MODEL: ${{ vars.LLM_MODEL || 'deepseek-chat' }}
      JUDGE_API_KEY: ${{ secrets.JUDGE_API_KEY }}
      JUDGE_BASE_URL: ${{ vars.JUDGE_BASE_URL }}
      JUDGE_MODEL: ${{ vars.JUDGE_MODEL }}
      SEARCH_PROVIDER: ${{ vars.SEARCH_PROVIDER || 'duckduckgo' }}
      SEARCH_API_KEY: ${{ secrets.SEARCH_API_KEY }}
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: uv sync --extra dev

      - name: Guard - API key configured
        run: |
          if [ -z "$LLM_API_KEY" ]; then
            echo "::error::LLM_API_KEY secret is not configured"
            exit 1
          fi

      - name: Run quality eval
        run: |
          ARGS="--spawn"
          if [ -n "${{ github.event.inputs.motions }}" ]; then
            ARGS="$ARGS --motions ${{ github.event.inputs.motions }}"
          else
            ARGS="$ARGS --limit ${{ github.event.inputs.limit }}"
          fi
          uv run python evals/quality/run_eval.py $ARGS

      - uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: evals/reports/
```

- [ ] **Step 7: Create `evals/README.md`**

```markdown
# Evaluation

Two tiers. 简体中文说明见下。

## Tier 1 — A2A Conformance Suite (offline, free)

Deterministic spec-compliance checks against any live A2A agent:

```bash
uv run python research_agent/main.py &
uv run python evals/conformance/suite.py --url http://localhost:8001
```

11 checks (agent card, SendMessage v1, millisecond timestamps, legacy aliases,
GetTask, error format, terminal continuation rejection, multi-turn, context
seeding, ListTasks, streaming chunks). Exit 0 iff all non-skipped checks pass.
`--json PATH` writes a machine-readable report. Runs in CI on every push.

## Tier 2 — Debate Quality Evals (LLM-as-judge, costs money)

```bash
uv run python evals/quality/run_eval.py --spawn --limit 3
```

Metrics per motion: citation coverage, link liveness (real HTTP checks),
claim-support rate and persona adherence (judged), trap-motion honesty
(false-premise motions must be challenged or declared unsupported).

Judge configuration: set `JUDGE_API_KEY` / `JUDGE_BASE_URL` / `JUDGE_MODEL`
for an independent judge; without them the runner falls back to `LLM_*` and
stamps the report `self_judged: true`.

Reports land in `evals/reports/` (gitignored) as JSON + Markdown.
CI: GitHub Actions workflow `Eval` (manual dispatch only).

## 中文说明

- 一致性套件：离线免费，对任意 A2A agent 打分（11 项检查），CI 每次 push 自动跑
- 质量评测：需要 LLM key，引用覆盖/链接存活为确定性指标，论断支持率与人格保持度由裁判模型打分；
  陷阱题考察"声明无据"而非配合幻觉。独立裁判用 `JUDGE_*` 环境变量，未配置回退 `LLM_*` 并标注自评
```

- [ ] **Step 8: Update READMEs, CHANGELOG, .gitignore**

- `README.md` + `README.zh-CN.md`: add a short "Evaluation / 评测" section after the debate demo section, pointing to `evals/README.md`, and add `evals/` to both project-structure trees.
- `.gitignore`: append `evals/reports/`.
- `CHANGELOG.md` under `## [Unreleased]` → `### Added`:

```markdown
- A2A 一致性套件 `evals/conformance/`：11 项协议检查对任意 agent 打分（CLI + JSON 报告），CI 每次 push 对 research/debate agent 自动运行
- 辩论质量评测 `evals/quality/`：15 题辩题集（含 3 道错误前提陷阱题）、引用覆盖率/链接存活率确定性指标、论断支持率/人格保持度 LLM-as-judge、独立裁判（`JUDGE_*` 回退 `LLM_*` 并标注自评）、JSON+Markdown 报告；GitHub Actions `Eval` 工作流手动触发
```

- [ ] **Step 9: Full verification**

```bash
uv run pytest test_a2a.py test_registry.py test_task_store.py test_search_tool.py test_debate_agent.py test_debate_flow.py test_conformance.py test_eval_quality.py test_eval_runner.py -q
uv run python test_e2e.py
uv run python test_web.py
uv run ruff check .
```
Expected: all green, lint clean.

- [ ] **Step 10: Commit and push**

```bash
git add evals/ .github/ test_eval_runner.py README.md README.zh-CN.md CHANGELOG.md .gitignore
git commit -m "feat: debate quality eval runner, CI conformance job, eval workflow and docs"
git push origin main
git push gitea main
```
