"""A2A v1.0 (JSON-RPC 绑定) 核心流程测试（TestClient / ASGITransport，无需真实端口）"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from research_agent.main import app as research_app
from writing_agent.main import app as writing_app
from orchestrator.main import A2AJSONRPCClient

CARD_PATH = "/.well-known/agent-card.json"
LEGACY_CARD_PATH = "/.well-known/agent.json"


def rpc(client, method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _send_research_message(message_id: str, text: str) -> dict:
    client = TestClient(research_app)
    rpc_resp = rpc(
        client,
        "SendMessage",
        {
            "message": {
                "messageId": message_id,
                "role": "ROLE_USER",
                "parts": [{"text": text}],
            }
        },
    )
    assert rpc_resp.get("error") is None, rpc_resp
    return rpc_resp["result"]


def test_agent_card_canonical_path():
    for name, app in [("research", research_app), ("writing", writing_app)]:
        client = TestClient(app)
        resp = client.get(CARD_PATH)
        assert resp.status_code == 200, f"{name} agent card failed"
        card = resp.json()
        assert "supportedInterfaces" in card, f"{name} missing supportedInterfaces"
        assert card["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
        assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
        assert "capabilities" in card
        print(f"[OK] {name} agent card: {card['name']}")


def test_agent_card_legacy_path_still_served():
    client = TestClient(research_app)
    resp = client.get(LEGACY_CARD_PATH)
    assert resp.status_code == 200
    assert "supportedInterfaces" in resp.json()
    print("[OK] legacy agent.json path still served")


def test_send_message_v1():
    task = _send_research_message("msg-001", "kubernetes")
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task["status"]
    assert task["artifacts"], "result should be in artifacts"
    text = task["artifacts"][0]["parts"][0]["text"]
    assert text, "artifact text should be non-empty"
    print(f"[OK] SendMessage: taskId={task['id']}, text_len={len(text)}")


def test_timestamp_millisecond_precision():
    task = _send_research_message("msg-ts", "timestamp check")
    ts = task["status"]["timestamp"]
    # 规范模式: YYYY-MM-DDTHH:mm:ss.sssZ
    assert ts.endswith("Z"), ts
    frac = ts.split(".")[-1][:-1]  # 去掉末尾 Z
    assert len(frac) == 3, f"expected millisecond precision, got: {ts}"
    print(f"[OK] timestamp format: {ts}")


def test_get_task_v1():
    task_id = _send_research_message("msg-get", "get task check")["id"]
    client = TestClient(research_app)
    rpc_resp = rpc(client, "GetTask", {"id": task_id})
    assert rpc_resp.get("error") is None, rpc_resp
    assert rpc_resp["result"]["id"] == task_id
    print("[OK] GetTask")


def test_legacy_method_alias():
    client = TestClient(research_app)
    payload = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tasks/send",
        "params": {
            "message": {
                "messageId": "msg-legacy",
                "role": "user",
                "parts": [{"text": "docker"}],
            }
        },
    }
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 200, resp.text
    rpc_resp = resp.json()
    assert rpc_resp.get("error") is None, rpc_resp
    assert rpc_resp["result"]["status"]["state"] == "TASK_STATE_COMPLETED"
    print("[OK] legacy tasks/send alias (with v0.x enum tolerance)")


def test_error_format_google_rpc_status():
    client = TestClient(research_app)
    rpc_resp = rpc(client, "GetTask", {"id": "nonexistent-task-id"})
    err = rpc_resp.get("error")
    assert err, "expected JSON-RPC error for unknown task"
    assert err["code"] == -32001, err
    data = err["data"]
    assert isinstance(data, list), f"data must be an array of ProtoJSON Any, got: {data}"
    info = data[0]
    assert info["@type"] == "type.googleapis.com/google.rpc.ErrorInfo"
    assert info["reason"] == "TASK_NOT_FOUND"
    assert info["domain"] == "a2a-protocol.org"
    print("[OK] google.rpc.ErrorInfo error format")


def test_send_message_does_not_block_event_loop():
    """慢任务执行期间，同一事件循环上的其他请求必须不被阻塞。"""
    import httpx
    from shared.a2a_server import A2AJSONRPCServer
    from shared.models import (
        AgentCapabilities,
        AgentCard,
        AgentInterface,
        Task,
        TaskState,
    )

    def slow_process(task: Task, store):
        store.update_status(task, TaskState.WORKING, "slow...")
        time.sleep(1.0)
        store.add_artifact(task, "response", "done")
        store.update_status(task, TaskState.COMPLETED, "done")

    card = AgentCard(
        name="slow-agent",
        description="test",
        supported_interfaces=[
            AgentInterface(url="http://test/rpc", protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    )
    app = A2AJSONRPCServer(agent_card=card, process_task=slow_process).build_app()

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:

            async def slow_request():
                r = await ac.post(
                    "/rpc",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "SendMessage",
                        "params": {
                            "message": {
                                "messageId": "m1",
                                "role": "ROLE_USER",
                                "parts": [{"text": "slow"}],
                            }
                        },
                    },
                )
                return r.json()

            slow_task = asyncio.create_task(slow_request())
            await asyncio.sleep(0.1)  # 让慢请求先进入处理
            t0 = time.monotonic()
            fast_resp = await ac.get("/")
            fast_elapsed = time.monotonic() - t0
            slow_result = await slow_task
            return fast_elapsed, fast_resp.status_code, slow_result

    fast_elapsed, fast_code, slow_result = asyncio.run(scenario())
    assert fast_code == 200
    assert fast_elapsed < 0.5, f"event loop was blocked: GET / took {fast_elapsed:.2f}s"
    assert slow_result["result"]["status"]["state"] == "TASK_STATE_COMPLETED"
    print(f"[OK] non-blocking: GET / during slow task took {fast_elapsed:.3f}s")


def test_orchestrator():
    client = A2AJSONRPCClient("http://localhost:8001")
    assert client.agent_url == "http://localhost:8001"
    assert client.rpc_url == "http://localhost:8001/rpc"
    print("[OK] A2AJSONRPCClient")


def test_model_serialization():
    from shared.models import AgentCard, AgentInterface

    card = AgentCard(
        name="test",
        description="test",
        supported_interfaces=[AgentInterface(url="http://x/rpc", protocol_binding="JSONRPC", protocol_version="1.0")],
        version="1.0.0",
        capabilities={"streaming": True},
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    )
    d = card.model_dump(by_alias=True, exclude_none=True)
    assert "supportedInterfaces" in d
    assert "protocolBinding" in d["supportedInterfaces"][0]
    print("[OK] model serialization")


def _build_test_agent(process_task, process_task_stream=None):
    """构建一个最小 A2A agent 应用，用于协议层行为测试。"""
    from shared.a2a_server import A2AJSONRPCServer
    from shared.models import AgentCapabilities, AgentCard, AgentInterface

    card = AgentCard(
        name="test-agent",
        description="test",
        supported_interfaces=[
            AgentInterface(url="http://test/rpc", protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=process_task_stream is not None),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    )
    return A2AJSONRPCServer(
        agent_card=card,
        process_task=process_task,
        process_task_stream=process_task_stream,
    ).build_app()


def _msg(mid, text, role="ROLE_USER", **extra):
    m = {"messageId": mid, "role": role, "parts": [{"text": text}]}
    m.update(extra)
    return m


def test_task_failure_sets_failed_state():
    """process_task 抛异常时，任务必须落到 TASK_STATE_FAILED 而不是卡在 WORKING。"""
    from shared.models import Task, TaskState

    def boom(task: Task, store):
        store.update_status(task, TaskState.WORKING, "working...")
        raise RuntimeError("LLM exploded")

    client = TestClient(_build_test_agent(boom))
    rpc_resp = rpc(client, "SendMessage", {"message": _msg("f1", "hello")})
    assert rpc_resp.get("error") is None, rpc_resp
    task = rpc_resp["result"]
    assert task["status"]["state"] == "TASK_STATE_FAILED", task["status"]
    status_text = task["status"]["message"]["parts"][0]["text"]
    assert "LLM exploded" in status_text

    # 失败任务仍可通过 GetTask 查询
    rpc_resp = rpc(client, "GetTask", {"id": task["id"]})
    assert rpc_resp["result"]["status"]["state"] == "TASK_STATE_FAILED"
    print("[OK] process_task exception -> TASK_STATE_FAILED")


def test_multi_turn_task_continuation():
    """INPUT_REQUIRED 任务通过 taskId 续聊，复用同一 task 并追加历史。"""
    from shared.models import Role, Task, TaskState

    def ask_for_more(task: Task, store):
        user_texts = [
            p.text for m in task.history if m.role == Role.USER for p in m.parts if p.text
        ]
        if len(user_texts) == 1:
            store.update_status(task, TaskState.WORKING, "thinking...")
            store.update_status(task, TaskState.INPUT_REQUIRED, "请补充更多细节")
        else:
            store.add_artifact(task, "response", f"answered: {' | '.join(user_texts)}")
            store.update_status(task, TaskState.COMPLETED, "done")

    client = TestClient(_build_test_agent(ask_for_more))

    first = rpc(client, "SendMessage", {"message": _msg("t1", "kubernetes")})
    task1 = first["result"]
    assert task1["status"]["state"] == "TASK_STATE_INPUT_REQUIRED", task1["status"]

    second = rpc(
        client,
        "SendMessage",
        {"message": _msg("t2", "聚焦 pod 调度", taskId=task1["id"], contextId=task1["contextId"])},
    )
    assert second.get("error") is None, second
    task2 = second["result"]
    assert task2["id"] == task1["id"], "continuation must reuse the same task"
    assert task2["status"]["state"] == "TASK_STATE_COMPLETED", task2["status"]
    user_turns = [m for m in task2["history"] if m["role"] == "ROLE_USER"]
    assert len(user_turns) == 2, "history must contain both user turns"
    text = task2["artifacts"][0]["parts"][0]["text"]
    assert "kubernetes" in text and "pod" in text
    print("[OK] multi-turn continuation via taskId")


def test_terminal_task_rejects_continuation():
    """终态（COMPLETED）任务不能再接收消息，返回 -32004 UnsupportedOperationError。"""
    from shared.models import Task, TaskState

    def one_shot(task: Task, store):
        store.update_status(task, TaskState.WORKING)
        store.add_artifact(task, "response", "ok")
        store.update_status(task, TaskState.COMPLETED)

    client = TestClient(_build_test_agent(one_shot))
    task = rpc(client, "SendMessage", {"message": _msg("d1", "hi")})["result"]

    rpc_resp = rpc(
        client,
        "SendMessage",
        {"message": _msg("d2", "again", taskId=task["id"])},
    )
    err = rpc_resp.get("error")
    assert err, "expected error for continuing a terminal task"
    assert err["code"] == -32004, err
    assert err["data"][0]["reason"] == "UNSUPPORTED_OPERATION"
    print("[OK] terminal task continuation rejected with -32004")


def test_context_continuation_seeds_history():
    """带 contextId 的新消息创建新 task，且能继承该上下文的历史消息。"""
    from shared.models import Task, TaskState

    def echo(task: Task, store):
        store.update_status(task, TaskState.WORKING)
        n = len([m for m in task.history if m.role])
        store.add_artifact(task, "response", f"turns={n}")
        store.update_status(task, TaskState.COMPLETED)

    client = TestClient(_build_test_agent(echo))
    t1 = rpc(client, "SendMessage", {"message": _msg("c1", "first")})["result"]
    t2 = rpc(
        client,
        "SendMessage",
        {"message": _msg("c2", "second", contextId=t1["contextId"])},
    )["result"]

    assert t2["id"] != t1["id"], "new task expected for context continuation"
    assert t2["contextId"] == t1["contextId"], "context must be preserved"
    first_texts = [p["text"] for m in t2["history"] for p in m["parts"] if p.get("text")]
    assert "first" in first_texts and "second" in first_texts, t2["history"]
    print("[OK] context continuation seeds history")


def test_streaming_artifact_chunks():
    """SendStreamingMessage + process_task_stream：增量 artifact 事件（append/lastChunk）。"""
    import json as _json

    def stream_process(task, store):
        for piece in ["Hello ", "stream ", "world"]:
            yield piece

    app = _build_test_agent(process_task=lambda t, s: None, process_task_stream=stream_process)
    client = TestClient(app)
    resp = client.post(
        "/rpc/stream",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendStreamingMessage",
            "params": {"message": _msg("s1", "hi")},
        },
    )
    assert resp.status_code == 200, resp.text
    events = [
        _json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]

    chunks = [e["artifactUpdate"] for e in events if "artifactUpdate" in e]
    assert len(chunks) >= 3, f"expected >=3 artifact chunks, got {len(chunks)}"
    assert chunks[0]["append"] is False, "first chunk starts a new artifact"
    assert all(c["append"] for c in chunks[1:]), "subsequent chunks must append"
    assert chunks[-1]["lastChunk"] is True, "final chunk must set lastChunk"
    artifact_ids = {c["artifact"]["artifactId"] for c in chunks}
    assert len(artifact_ids) == 1, "chunks must reference the same artifact"
    assembled = "".join(c["artifact"]["parts"][0]["text"] for c in chunks)
    assert assembled == "Hello stream world", assembled

    # 任务终态 + 完整 artifact 落库
    task_id = [e["task"]["id"] for e in events if "task" in e][0]
    final_states = [
        e["statusUpdate"]["status"]["state"]
        for e in events
        if "statusUpdate" in e
    ]
    assert "TASK_STATE_COMPLETED" in final_states, final_states
    got = rpc(client, "GetTask", {"id": task_id})["result"]
    assert got["status"]["state"] == "TASK_STATE_COMPLETED"
    assert got["artifacts"][0]["parts"][0]["text"] == "Hello stream world"
    print(f"[OK] streaming: {len(chunks)} chunks, assembled={assembled!r}")


def test_streaming_generator_failure_marks_failed():
    """流式生成器抛异常时任务落 TASK_STATE_FAILED，SSE 正常收尾。"""
    import json as _json

    def bad_stream(task, store):
        yield "partial..."
        raise RuntimeError("stream boom")

    app = _build_test_agent(process_task=lambda t, s: None, process_task_stream=bad_stream)
    client = TestClient(app)
    resp = client.post(
        "/rpc/stream",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendStreamingMessage",
            "params": {"message": _msg("s2", "hi")},
        },
    )
    assert resp.status_code == 200, resp.text
    events = [
        _json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    states = [e["statusUpdate"]["status"]["state"] for e in events if "statusUpdate" in e]
    assert "TASK_STATE_FAILED" in states, states
    task_id = [e["task"]["id"] for e in events if "task" in e][0]
    got = rpc(client, "GetTask", {"id": task_id})["result"]
    assert got["status"]["state"] == "TASK_STATE_FAILED"
    print("[OK] streaming failure -> TASK_STATE_FAILED")


def test_research_streaming_failure_marks_failed(monkeypatch):
    """research agent 流式中途失败必须落 TASK_STATE_FAILED，不得静默截断。"""
    import json as _json
    import research_agent.main as research_module

    def bad_stream(system, user, **kw):
        def gen():
            yield "partial..."
            raise RuntimeError("llm stream boom")

        return gen()

    monkeypatch.setattr(research_module, "call_llm_stream", bad_stream)
    client = TestClient(research_app)
    resp = client.post(
        "/rpc/stream",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendStreamingMessage",
            "params": {"message": _msg("m-rf", "hello")},
        },
    )
    assert resp.status_code == 200, resp.text
    events = [
        _json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    states = [e["statusUpdate"]["status"]["state"] for e in events if "statusUpdate" in e]
    assert "TASK_STATE_FAILED" in states, states
    task_id = [e["task"]["id"] for e in events if "task" in e][0]
    got = rpc(client, "GetTask", {"id": task_id})["result"]
    assert got["status"]["state"] == "TASK_STATE_FAILED"
    print("[OK] research streaming failure -> TASK_STATE_FAILED")


def test_cancel_race_keeps_canceled_state():
    """取消 WORKING 任务后，工作线程迟到的完成写入不得覆盖 CANCELED。

    用 ASGITransport + 持久事件循环，保证 returnImmediately 的后台任务真实运行。
    """
    import asyncio
    import httpx
    from shared.models import Task, TaskState

    def slow_complete(task: Task, store):
        store.update_status(task, TaskState.WORKING, "working...")
        time.sleep(0.8)
        store.add_artifact(task, "response", "late result")
        store.update_status(task, TaskState.COMPLETED, "done")

    app = _build_test_agent(slow_complete)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/rpc",
                json={
                    "jsonrpc": "2.0", "id": 1, "method": "SendMessage",
                    "params": {
                        "message": {"messageId": "m-cancel", "role": "ROLE_USER",
                                    "parts": [{"text": "hello"}]},
                        "configuration": {"returnImmediately": True},
                    },
                },
            )
            task = r.json()["result"]
            await asyncio.sleep(0.4)  # worker 已进入 WORKING
            r2 = await ac.post(
                "/rpc",
                json={"jsonrpc": "2.0", "id": 2, "method": "CancelTask",
                      "params": {"id": task["id"]}},
            )
            assert r2.json()["result"]["status"]["state"] == "TASK_STATE_CANCELED"
            await asyncio.sleep(0.8)  # worker 迟到的 add_artifact / COMPLETED
            r3 = await ac.post(
                "/rpc",
                json={"jsonrpc": "2.0", "id": 3, "method": "GetTask",
                      "params": {"id": task["id"]}},
            )
            return r3.json()["result"]

    final = asyncio.run(scenario())
    assert final["status"]["state"] == "TASK_STATE_CANCELED", final["status"]
    assert not final.get("artifacts"), "late artifact must not land after cancel"


def test_cancel_unknown_task_error_code():
    """CancelTask 的任务未找到错误码必须与 GetTask 一致（-32001）。"""
    client = TestClient(research_app)
    rpc_resp = rpc(client, "CancelTask", {"id": "nonexistent-id"})
    err = rpc_resp["error"]
    assert err["code"] == -32001, err
    assert err["data"][0]["reason"] == "TASK_NOT_FOUND"


if __name__ == "__main__":
    test_model_serialization()
    test_agent_card_canonical_path()
    test_agent_card_legacy_path_still_served()
    test_send_message_v1()
    test_timestamp_millisecond_precision()
    test_get_task_v1()
    test_legacy_method_alias()
    test_error_format_google_rpc_status()
    test_send_message_does_not_block_event_loop()
    test_task_failure_sets_failed_state()
    test_multi_turn_task_continuation()
    test_terminal_task_rejects_continuation()
    test_context_continuation_seeds_history()
    test_streaming_artifact_chunks()
    test_streaming_generator_failure_marks_failed()
    # test_research_streaming_failure_marks_failed 依赖 monkeypatch，pytest 下运行
    test_orchestrator()
    print("\nAll A2A core tests passed!")
