"""
通用 LLM 客户端
支持 OpenAI 兼容 API（OpenAI、DeepSeek、SiliconFlow、Ollama、vLLM 等）
"""

import os
import warnings
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def _get_client() -> Optional[OpenAI]:
    """根据环境变量创建 OpenAI 兼容客户端"""
    if OpenAI is None:
        warnings.warn("openai package not installed, LLM disabled")
        return None

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")

    if not api_key and not base_url:
        # 本地 Ollama 默认不需要 key
        if os.getenv("LLM_MODEL", "").startswith("ollama/"):
            pass
        else:
            return None

    client_kwargs = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    if base_url:
        client_kwargs["base_url"] = base_url

    return OpenAI(**client_kwargs)


def call_llm(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
) -> Optional[str]:
    """
    调用 LLM 生成文本。
    如果未配置 LLM 环境变量，返回 None，调用方应回退到本地逻辑。
    """
    client = _get_client()
    if client is None:
        return None

    model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")

    # 兼容 litellm / ollama 风格的前缀
    if model.startswith("ollama/"):
        model = model.replace("ollama/", "")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content
    except Exception as e:
        warnings.warn(f"LLM call failed: {e}")
        return None
