"""End-to-end test: start all 3 services via subprocess and test via HTTP."""

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

        # Test agent card (v1.0 canonical path)
        for port in [8001, 8002]:
            with httpx.Client(trust_env=False, timeout=5) as client:
                r = client.get(f"http://localhost:{port}/.well-known/agent-card.json")
            r.raise_for_status()
            card = r.json()
            assert "supportedInterfaces" in card
            print(f"[OK] agent card on {port}: {card['name']}")

        # Test SendMessage on research agent (v1.0 method names / enums)
        task = rpc_call(
            8001,
            "SendMessage",
            {
                "message": {
                    "messageId": "e2e-001",
                    "role": "ROLE_USER",
                    "parts": [{"text": "docker"}],
                }
            },
        )
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert task["artifacts"]
        print(f"[OK] research SendMessage: {task['id']}")

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
