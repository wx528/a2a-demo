"""LLM 真实链路冒烟测试（需要真实 API Key，CI 中按需触发）。

验证内容：
1. SendMessage 阻塞调用返回真实 LLM 输出（非本地回退文案）
2. SendStreamingMessage 真流式（多个 artifact 增量块 + lastChunk 收尾）
3. orchestrator 完整工作流（research -> writing）

用法：
    LLM_API_KEY=sk-... LLM_BASE_URL=https://api.deepseek.com/v1 LLM_MODEL=deepseek-chat \
        uv run python test_llm_smoke.py
"""

import json
import os
import subprocess
import sys
import time

import httpx

try:
    import pytest

    pytestmark = pytest.mark.skipif(
        not os.getenv("LLM_API_KEY"), reason="LLM_API_KEY not set"
    )
except ImportError:
    pytest = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FALLBACK_MARKER = "LLM 服务不可用"


def start_service(name, port, main_file, extra_env=None):
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = "localhost"
    if extra_env:
        env.update(extra_env)
    return subprocess.Popen(
        [sys.executable, main_file],
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_ready(url, timeout=30):
    start = time.time()
    with httpx.Client(trust_env=False, timeout=3) as client:
        while time.time() - start < timeout:
            try:
                if client.get(url).status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
    return False


def rpc_call(port, method, params):
    with httpx.Client(trust_env=False, timeout=300) as client:
        r = client.post(
            f"http://localhost:{port}/rpc",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        r.raise_for_status()
        resp = r.json()
    if resp.get("error"):
        raise RuntimeError(f"RPC error: {resp['error']}")
    return resp["result"]


def artifact_text(task):
    return task["artifacts"][0]["parts"][0]["text"]


def test_blocking_send_returns_real_llm_output():
    task = rpc_call(
        8001,
        "SendMessage",
        {
            "message": {
                "messageId": "smoke-1",
                "role": "ROLE_USER",
                "parts": [{"text": "用一句话解释什么是 Kubernetes，20 字以内。"}],
            }
        },
    )
    assert task["status"]["state"] == "TASK_STATE_COMPLETED", task["status"]
    text = artifact_text(task)
    assert text, "artifact text empty"
    assert FALLBACK_MARKER not in text, f"got fallback text: {text!r}"
    assert len(text) >= 5, f"suspiciously short: {text!r}"
    print(f"[OK] blocking send, real output: {text[:50]}...")


def test_streaming_has_multiple_chunks():
    chunk_count = 0
    last_chunk_seen = False
    completed_seen = False
    with httpx.Client(trust_env=False, timeout=300) as client:
        with client.stream(
            "POST",
            "http://localhost:8001/rpc/stream",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "SendStreamingMessage",
                "params": {
                    "message": {
                        "messageId": "smoke-2",
                        "role": "ROLE_USER",
                        "parts": [{"text": "用三句话介绍 Docker 的核心概念。"}],
                    }
                },
            },
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[len("data: "):])
                if "artifactUpdate" in event:
                    chunk_count += 1
                    if event["artifactUpdate"].get("lastChunk"):
                        last_chunk_seen = True
                    text = event["artifactUpdate"]["artifact"]["parts"][0]["text"]
                    assert FALLBACK_MARKER not in text, "stream fell back to template"
                if "statusUpdate" in event:
                    state = event["statusUpdate"]["status"]["state"]
                    if state == "TASK_STATE_COMPLETED":
                        completed_seen = True

    assert chunk_count >= 2, f"expected real token streaming, got {chunk_count} chunk(s)"
    assert last_chunk_seen, "stream must end with lastChunk=true"
    assert completed_seen, "stream must reach TASK_STATE_COMPLETED"
    print(f"[OK] streaming: {chunk_count} chunks, lastChunk + completed")


def test_orchestrator_workflow():
    with httpx.Client(trust_env=False, timeout=300) as client:
        r = client.post(
            "http://localhost:8000/create-article", json={"topic": "docker"}
        )
        r.raise_for_status()
        result = r.json()
    assert FALLBACK_MARKER not in result["research_summary"], result
    assert FALLBACK_MARKER not in result["article"], result
    assert len(result["article"]) > 50, "article too short for real LLM output"
    print(
        f"[OK] orchestrator: research_len={len(result['research_summary'])}, "
        f"article_len={len(result['article'])}"
    )


def main():
    if not os.getenv("LLM_API_KEY"):
        print("LLM_API_KEY not set -> skip smoke test")
        return 0

    procs = []
    try:
        procs.append(start_service("research", 8001, "research_agent/main.py"))
        procs.append(start_service("writing", 8002, "writing_agent/main.py"))
        procs.append(
            start_service(
                "orchestrator",
                8000,
                "orchestrator/main.py",
                extra_env={
                    "RESEARCH_AGENT_URL": "http://localhost:8001",
                    "WRITING_AGENT_URL": "http://localhost:8002",
                },
            )
        )
        for url in [
            "http://localhost:8001/",
            "http://localhost:8002/",
            "http://localhost:8000/",
        ]:
            assert wait_for_ready(url), f"service not ready: {url}"

        test_blocking_send_returns_real_llm_output()
        test_streaming_has_multiple_chunks()
        test_orchestrator_workflow()
        print("\nAll LLM smoke tests passed!")
        return 0
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
