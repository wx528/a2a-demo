"""End-to-end test: start all 3 services via subprocess and test via HTTP."""

import json
import os
import subprocess
import sys
import time

import httpx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def start_service(name, port, main_file, extra_env=None):
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = "localhost"
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, main_file],
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def wait_for_ready(url, timeout=30):
    start = time.time()
    last_err = None
    # trust_env=False 避免 Windows 上 httpx 读取系统代理导致 502
    client = httpx.Client(trust_env=False, timeout=3)
    while time.time() - start < timeout:
        try:
            r = client.get(url)
            if r.status_code == 200:
                client.close()
                return True
            last_err = f"status {r.status_code}"
        except Exception as e:
            last_err = str(e)
        time.sleep(0.5)
    client.close()
    print(f"Timeout waiting for {url}, last: {last_err}")
    return False


def rpc_call(port, method, params, req_id=1):
    url = f"http://localhost:{port}/rpc"
    payload = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params,
    }
    with httpx.Client(trust_env=False, timeout=60) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        resp = r.json()
    if resp.get("error"):
        raise RuntimeError(f"RPC error: {resp['error']}")
    return resp["result"]


def main():
    procs = []
    try:
        print("Starting services...")
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

        print("Waiting for readiness...")
        assert wait_for_ready("http://localhost:8001/"), "research not ready"
        assert wait_for_ready("http://localhost:8002/"), "writing not ready"
        assert wait_for_ready("http://localhost:8000/"), "orchestrator not ready"
        print("All services ready")

        # Test agent card
        for port in [8001, 8002]:
            with httpx.Client(trust_env=False, timeout=5) as client:
                r = client.get(f"http://localhost:{port}/.well-known/agent.json")
            r.raise_for_status()
            card = r.json()
            assert "supportedInterfaces" in card
            print(f"[OK] agent card on {port}: {card['name']}")

        # Test tasks/send on research agent
        task = rpc_call(
            8001,
            "tasks/send",
            {
                "message": {
                    "messageId": "e2e-001",
                    "role": "user",
                    "parts": [{"text": "docker"}],
                }
            },
        )
        assert task["status"]["state"] == "completed"
        assert task["artifacts"]
        print(f"[OK] research tasks/send: {task['id']}")

        # Test orchestrator workflow
        with httpx.Client(trust_env=False, timeout=120) as client:
            r = client.post(
                "http://localhost:8000/create-article",
                json={"topic": "docker"},
            )
        r.raise_for_status()
        result = r.json()
        assert result["research_summary"]
        assert result["article"]
        print(
            f"[OK] orchestrator workflow: research_len={len(result['research_summary'])}, "
            f"article_len={len(result['article'])}"
        )

        print("\nAll e2e tests passed!")
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
