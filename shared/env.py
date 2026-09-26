"""
本地开发 .env 加载器。

让 `python research_agent/main.py` 这类裸跑（不用 docker compose）也能
自动读取仓库根目录的 `.env`；docker compose 场景本来就通过变量替换读 .env。

规则：
- 已存在的环境变量优先（override=False，显式 export 覆盖 .env）
- 文件不存在时静默跳过
- 必须在读取任何 LLM_* / *_AGENT_URL / PORT 等变量之前调用
"""

from pathlib import Path
from typing import Optional, Union


def load_env(path: Optional[Union[str, Path]] = None, override: bool = False) -> bool:
    """加载 .env（默认仓库根目录，即 shared/ 的上一级）。返回是否找到并加载。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    if path is None:
        path = Path(__file__).resolve().parent.parent / ".env"
    return load_dotenv(dotenv_path=str(path), override=override)
