"""
AgentRegistry - 基于 Agent Card 的动态发现与解析。

启动时从各 agent 的 /.well-known/agent-card.json 拉取卡片完成注册，
之后可按 card 名称 / 短名 / skill id 解析出 agent 地址，
新增 agent 无需改编排代码。
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("orchestrator.registry")

_DISCOVERY_TIMEOUT = 10.0


class AgentRegistry:
    def __init__(self):
        # card["name"] -> {"url": base_url, "card": card}
        self._agents: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    def register(self, url: str, card: Optional[Dict[str, Any]] = None):
        """注册一个 agent；不传 card 时现场拉取（发现）。"""
        if card is None:
            card = self._fetch_card(url)
        self._agents[card["name"]] = {"url": url.rstrip("/"), "card": card}
        logger.info("registered agent %s at %s", card["name"], url)

    async def discover(self, urls: List[str]):
        """批量发现：逐个拉取 card，失败的跳过并记录日志。"""
        for url in urls:
            if not url:
                continue
            try:
                card = await self._fetch_card_async(url)
            except Exception as e:
                logger.warning("discovery failed for %s: %s", url, e)
                continue
            self.register(url, card)

    @staticmethod
    def _fetch_card(url: str) -> Dict[str, Any]:
        with httpx.Client(timeout=_DISCOVERY_TIMEOUT, trust_env=False) as client:
            resp = client.get(f"{url.rstrip('/')}/.well-known/agent-card.json")
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def _fetch_card_async(url: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT, trust_env=False) as client:
            resp = await client.get(f"{url.rstrip('/')}/.well-known/agent-card.json")
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list(self) -> List[Dict[str, Any]]:
        return [info["card"] for info in self._agents.values()]

    def names(self) -> List[str]:
        return list(self._agents.keys())

    def resolve(self, name: str) -> Optional[str]:
        """按 card 名称 / 短名（去掉 -agent 后缀）/ skill id 解析 agent 地址。"""
        if not name:
            return None
        if name in self._agents:
            return self._agents[name]["url"]
        # 短名：research -> research-agent
        for card_name in self._agents:
            if card_name.split("-agent")[0] == name:
                return self._agents[card_name]["url"]
        # skill id
        for info in self._agents.values():
            for skill in info["card"].get("skills", []):
                if skill.get("id") == name:
                    return info["url"]
        return None

    def find_by_skill(self, skill: str) -> Optional[str]:
        """按 skill id / 标签名找到具备该能力的 agent 地址。"""
        for info in self._agents.values():
            for s in info["card"].get("skills", []):
                if s.get("id") == skill or skill in (s.get("tags") or []):
                    return info["url"]
        return None
