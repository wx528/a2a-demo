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
    # 探针文本优先用 card 声明的输入示例（不同 agent 的输入契约不同，
    # 例如 debate agent 要求 [辩题/MOTION] 段落开头的消息）
    probe = "conformance probe"
    for skill in card.get("skills", []):
        examples = skill.get("examples") or []
        if examples:
            probe = examples[0]
            break
    ctx["probe"] = probe
    if problems:
        return CheckResult("agent-card", "FAIL", f"missing: {problems}")
    return CheckResult("agent-card", "PASS", card["name"])


@check
async def send_message_v1(client, ctx):
    resp = await client.call_raw("SendMessage", _msg(ctx.get("probe", "conformance probe"), "cf-1"))
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
    payload = {"message": {"messageId": "cf-legacy", "role": "user", "parts": [{"text": ctx.get("probe", "legacy probe")}]}}
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
    events = await client.stream_send(ctx.get("probe", "conformance streaming probe"))
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
