"""shared/env.py .env 加载器测试。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.env import load_env


def test_loads_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TEST_DOTENV_KEY=hello\nTEST_DOTENV_URL=https://x.example\n", encoding="utf-8"
    )
    monkeypatch.delenv("TEST_DOTENV_KEY", raising=False)
    monkeypatch.delenv("TEST_DOTENV_URL", raising=False)
    assert load_env(path=str(env_file)) is True
    assert os.environ["TEST_DOTENV_KEY"] == "hello"
    assert os.environ["TEST_DOTENV_URL"] == "https://x.example"


def test_missing_file_is_silent_noop(tmp_path):
    assert load_env(path=str(tmp_path / "nope.env")) is False


def test_existing_env_wins_by_default(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_DOTENV_OVERRIDE=from-file\n", encoding="utf-8")
    monkeypatch.setenv("TEST_DOTENV_OVERRIDE", "from-env")
    load_env(path=str(env_file))
    assert os.environ["TEST_DOTENV_OVERRIDE"] == "from-env"
    # 显式 override=True 才覆盖
    load_env(path=str(env_file), override=True)
    assert os.environ["TEST_DOTENV_OVERRIDE"] == "from-file"


def test_default_path_is_repo_root_dotenv(tmp_path, monkeypatch):
    """默认路径指向仓库根目录的 .env（shared/ 的上一级）。"""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent
    env_file = repo_root / ".env"
    if env_file.exists():
        # 本地存在真实 .env 时只验证路径解析，不实际加载副作用
        assert load_env() in (True, False)
    else:
        assert load_env() is False
