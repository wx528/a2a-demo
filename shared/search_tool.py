"""
搜索工具层：给 agent 提供带链接的网络检索能力。

Provider 通过环境变量选择（对齐 LLM_* 的风格）：
    SEARCH_PROVIDER=duckduckgo（默认，无需 key）| tavily（需 SEARCH_API_KEY）
    SEARCH_MAX_RESULTS=5

任何失败（无网络 / 无 key / 服务不可用）一律返回空列表，绝不抛异常。
"""

import os
import warnings
from typing import Dict, List

import httpx


def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """检索并返回 [{"title", "url", "snippet"}]，按 URL 去重。失败返回 []。"""
    if not query or not query.strip():
        return []
    cap = int(os.getenv("SEARCH_MAX_RESULTS", "5") or 5)
    max_results = min(max_results, cap) if cap > 0 else max_results

    provider = os.getenv("SEARCH_PROVIDER", "duckduckgo").lower()
    try:
        if provider == "tavily":
            raw = _search_tavily(query, max_results)
        else:
            raw = _search_duckduckgo(query, max_results)
    except Exception as e:
        warnings.warn(f"web_search failed ({provider}): {e}")
        return []

    seen = set()
    results = []
    for item in raw:
        url = item.get("url") or item.get("href") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        results.append(
            {
                "title": item.get("title") or "",
                "url": url,
                "snippet": item.get("snippet") or item.get("body") or "",
            }
        )
    return results


def _search_duckduckgo(query: str, max_results: int) -> List[Dict[str, str]]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


def _search_tavily(query: str, max_results: int) -> List[Dict[str, str]]:
    api_key = os.getenv("SEARCH_API_KEY", "")
    if not api_key:
        warnings.warn("SEARCH_API_KEY not set; tavily search skipped")
        return []
    resp = httpx.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"query": query, "max_results": max_results},
        timeout=15.0,
        trust_env=False,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])
    ]
