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
from debate_agent.main import app as debate_app
from evals.conformance.checks import run_suite

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8791
URL = f"http://127.0.0.1:{PORT}"
DEBATE_PORT = 8792
DEBATE_URL = f"http://127.0.0.1:{DEBATE_PORT}"


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


@pytest.fixture(scope="module")
def debate_server():
    import uvicorn

    config = uvicorn.Config(debate_app, host="127.0.0.1", port=DEBATE_PORT, log_level="error")
    srv = uvicorn.Server(config)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    with httpx.Client(trust_env=False, timeout=3) as c:
        for _ in range(60):
            try:
                if c.get(f"{DEBATE_URL}/").status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
    yield DEBATE_URL
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


def test_all_checks_pass_against_debate_agent(debate_server):
    """探针文本取自 card 的 skills[].examples（debate agent 要求 [辩题/MOTION] 输入）。"""
    results = asyncio.run(run_suite(debate_server))
    failed = [(r.name, r.detail) for r in results if r.status == "FAIL"]
    assert not failed, failed
    skipped = [r.name for r in results if r.status == "SKIP"]
    assert skipped == ["multi-turn-continuation"], skipped


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
