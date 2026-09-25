"""shared/search_tool.py 单元测试：provider 选择、失败降级、永不抛异常。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared import search_tool


def test_returns_list_of_dicts_shape(monkeypatch):
    def fake_ddg(query, max_results):
        return [{"title": "t", "href": "https://x", "body": "s"}]

    monkeypatch.setattr(search_tool, "_search_duckduckgo", fake_ddg)
    results = search_tool.web_search("kubernetes", max_results=3)
    assert results == [{"title": "t", "url": "https://x", "snippet": "s"}]


def test_provider_selection_tavily(monkeypatch):
    called = {}

    def fake_tavily(query, max_results):
        called["q"] = query
        return [{"title": "t", "url": "https://t", "snippet": "s"}]

    monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("SEARCH_API_KEY", "sk-test")
    monkeypatch.setattr(search_tool, "_search_tavily", fake_tavily)
    assert search_tool.web_search("q")[0]["url"] == "https://t"
    assert called["q"] == "q"


def test_never_raises_on_provider_error(monkeypatch):
    def boom(query, max_results):
        raise RuntimeError("network down")

    monkeypatch.setattr(search_tool, "_search_duckduckgo", boom)
    assert search_tool.web_search("anything") == []


def test_non_numeric_max_results_env_returns_empty(monkeypatch):
    monkeypatch.setenv("SEARCH_MAX_RESULTS", "abc")
    monkeypatch.setattr(search_tool, "_search_duckduckgo", lambda q, max_results: [])
    assert search_tool.web_search("x") == []


def test_max_results_env_caps_provider_limit(monkeypatch):
    captured = {}

    def fake(query, max_results):
        captured["max_results"] = max_results
        return []

    monkeypatch.setenv("SEARCH_MAX_RESULTS", "1")
    monkeypatch.setattr(search_tool, "_search_duckduckgo", fake)
    search_tool.web_search("q", max_results=5)
    assert captured["max_results"] == 1


def test_dedupe_and_cap(monkeypatch):
    def fake(query, max_results):
        return [
            {"title": "a", "href": "https://same", "body": "1"},
            {"title": "b", "href": "https://same", "body": "2"},
            {"title": "c", "href": "https://other", "body": "3"},
        ]

    monkeypatch.setattr(search_tool, "_search_duckduckgo", fake)
    results = search_tool.web_search("q", max_results=5)
    assert [r["url"] for r in results] == ["https://same", "https://other"]
