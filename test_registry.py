"""Orchestrator AgentRegistry（动态发现/解析）单元测试。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.registry import AgentRegistry


def _card(name, skills):
    return {
        "name": name,
        "description": f"card of {name}",
        "version": "1.0.0",
        "supportedInterfaces": [
            {"url": f"http://{name}/rpc", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
        "capabilities": {},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": skills,
    }


def _seed():
    reg = AgentRegistry()
    reg.register("http://research:8001", _card("research-agent", [
        {"id": "research", "name": "主题研究", "description": "d", "tags": ["research", "summary"]},
    ]))
    reg.register("http://writing:8002", _card("writing-agent", [
        {"id": "write-article", "name": "文章写作", "description": "d", "tags": ["writing"]},
    ]))
    return reg


def test_register_and_list():
    reg = _seed()
    assert len(reg.list()) == 2
    assert "research-agent" in reg.names()


def test_resolve_by_card_name():
    reg = _seed()
    assert reg.resolve("research-agent") == "http://research:8001"


def test_resolve_by_short_name():
    reg = _seed()
    assert reg.resolve("research") == "http://research:8001"
    assert reg.resolve("writing") == "http://writing:8002"


def test_resolve_by_skill_id():
    reg = _seed()
    assert reg.resolve("write-article") == "http://writing:8002"


def test_resolve_unknown_returns_none():
    reg = _seed()
    assert reg.resolve("nope") is None


def test_find_by_skill():
    reg = _seed()
    assert reg.find_by_skill("research") == "http://research:8001"
    assert reg.find_by_skill("writing") == "http://writing:8002"
    assert reg.find_by_skill("nothing") is None


def test_register_overwrites_same_name():
    reg = _seed()
    reg.register("http://research:9000", _card("research-agent", [
        {"id": "research", "name": "主题研究", "description": "d", "tags": []},
    ]))
    assert reg.resolve("research") == "http://research:9000"
    assert len(reg.list()) == 2


if __name__ == "__main__":
    test_register_and_list()
    test_resolve_by_card_name()
    test_resolve_by_short_name()
    test_resolve_by_skill_id()
    test_resolve_unknown_returns_none()
    test_find_by_skill()
    test_register_overwrites_same_name()
    print("\nAll registry tests passed!")
