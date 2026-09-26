"""Web 会议室 A2A 集成测试：启动 web + agent 服务，验证 SSE 流程。"""

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
    # 强制回退模式：保持测试离线确定性（真 LLM 链路由 test_llm_smoke 覆盖）
    env["LLM_API_KEY"] = ""
    env["LLM_BASE_URL"] = ""
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
    client = httpx.Client(trust_env=False, timeout=3)
    while time.time() - start < timeout:
        try:
            r = client.get(url)
            if r.status_code == 200:
                client.close()
                return True
        except Exception:
            pass
        time.sleep(0.5)
    client.close()
    return False


def parse_sse_events(text: str):
    """简单解析 SSE 文本，返回 [(event, data_json), ...]"""
    events = []
    current_event = None
    current_data = []
    for line in text.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: "):]
        elif line.startswith("data: "):
            current_data.append(line[len("data: "):])
        elif line == "" and current_event is not None:
            events.append((current_event, "".join(current_data)))
            current_event = None
            current_data = []
    if current_event is not None:
        events.append((current_event, "".join(current_data)))
    return events


def main():
    procs = []
    try:
        print("Starting services...")
        procs.append(start_service("research", 8001, "research_agent/main.py"))
        procs.append(start_service("writing", 8002, "writing_agent/main.py"))
        procs.append(
            start_service(
                "web",
                8080,
                "web/main.py",
                extra_env={
                    "RESEARCH_AGENT_URL": "http://localhost:8001",
                    "WRITING_AGENT_URL": "http://localhost:8002",
                },
            )
        )

        print("Waiting for readiness...")
        assert wait_for_ready("http://localhost:8001/"), "research not ready"
        assert wait_for_ready("http://localhost:8002/"), "writing not ready"
        assert wait_for_ready("http://localhost:8080/"), "web not ready"
        print("All services ready")

        # 创建会议室
        with httpx.Client(trust_env=False, timeout=10) as client:
            r = client.post(
                "http://localhost:8080/api/meetings",
                json={"topic": "docker", "mode": "pipeline"},
            )
        r.raise_for_status()
        meeting = r.json()
        meeting_id = meeting["id"]
        print(f"[OK] created meeting: {meeting_id}")

        # 读取 SSE 流一段时间，收集 agent 发言
        with httpx.Client(trust_env=False, timeout=120) as client:
            with client.stream(
                "GET", f"http://localhost:8080/api/meetings/{meeting_id}/events"
            ) as stream:
                # 读取足够字节数后关闭（流不会自己结束，除非 meeting 结束）
                collected = []
                for chunk in stream.iter_text():
                    collected.append(chunk)
                    # research + writing + review + code + summary 每个 agent 都会有 message 事件
                    if len("".join(collected)) > 3000:
                        break
                sse_text = "".join(collected)

        events = parse_sse_events(sse_text)
        message_events = [e for e in events if e[0] == "message"]
        agent_speakers = set()
        for event, data in message_events:
            try:
                msg = __import__("json").loads(data)
                if msg.get("participant_id") in ["research", "writing", "review", "code", "summary"]:
                    agent_speakers.add(msg["participant_id"])
            except Exception:
                pass

        print(f"[OK] agent speakers observed: {agent_speakers}")
        assert "research" in agent_speakers, "research should speak"
        assert "writing" in agent_speakers, "writing should speak"

        print("\nWeb A2A integration test passed!")
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
