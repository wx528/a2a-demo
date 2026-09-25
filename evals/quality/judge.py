"""LLM-as-judge：独立裁判（JUDGE_* env，未配置回退 LLM_*，报告标注 self_judged）。"""

import json
import os
import re
import warnings
from typing import Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


class Judge:
    def __init__(self):
        self.api_key = os.getenv("JUDGE_API_KEY") or os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("JUDGE_BASE_URL") or os.getenv("LLM_BASE_URL")
        self.model = os.getenv("JUDGE_MODEL") or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.self_judged = not os.getenv("JUDGE_API_KEY") and bool(self.api_key)
        self._client = None
        if self.api_key and OpenAI:
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)

    @property
    def available(self) -> bool:
        return self._client is not None

    def ask_json(self, system: str, user: str, max_tokens: int = 800) -> Optional[dict]:
        """请求严格 JSON 输出；解析失败重试一次；连续失败返回 None（调用方记 unparsed）。"""
        if not self.available:
            return None
        for _ in range(2):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
                raw = resp.choices[0].message.content or ""
                parsed = extract_json(raw)
                if parsed is not None:
                    return parsed
            except Exception as e:
                warnings.warn(f"judge call failed: {e}")
                return None
        return None


def extract_json(text: str) -> Optional[dict]:
    """从模型输出中提取 JSON 对象（容忍 ```json 围栏与前后噪声）。"""
    if not text:
        return None
    candidates = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        candidates.append(fence.group(1))
    brace = re.search(r"\{.*\}", text, re.S)
    if brace:
        candidates.append(brace.group(0))
    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def judge_claim_support(turn_text: str, sources: List[Dict[str, str]], judge: Judge) -> List[dict]:
    """逐引用判定 supported / unsupported / unrelated；解析失败记 unparsed。"""
    src_lines = "\n".join(f"- {s['url']}:\n{s['snippet'][:800]}" for s in sources)
    system = (
        "你是事实核查员。对辩手论点中引用的每个来源，判定它对该论点的支持情况。"
        '只输出 JSON：{"verdicts":[{"url":"...","verdict":"supported|unsupported|unrelated"}]}'
    )
    user = f"辩手论点：\n{turn_text[:2500]}\n\n来源：\n{src_lines}"
    parsed = judge.ask_json(system, user)
    verdicts = (parsed or {}).get("verdicts")
    if not isinstance(verdicts, list):
        return [{"url": s["url"], "verdict": "unparsed"} for s in sources]
    return verdicts


def judge_persona_adherence(persona_style: str, turn_text: str, judge: Judge) -> int:
    """人格保持度 1-5 分；0 表示未能解析。"""
    system = "你是辩论评审。评估辩手发言对人格风格的保持程度，1-5 分。只输出 JSON：{\"score\": <1-5>}"
    user = f"人格风格：{persona_style}\n\n发言：\n{turn_text[:2000]}"
    parsed = judge.ask_json(system, user)
    score = (parsed or {}).get("score")
    try:
        return max(1, min(5, int(score)))
    except (TypeError, ValueError):
        return 0


def judge_premise_challenge(motion_text: str, transcript: str, judge: Judge) -> bool:
    """陷阱题：辩手是否质疑了错误前提而非顺着发挥。"""
    system = (
        "你是评审。辩题包含错误前提，评估辩手是否质疑了前提本身而非顺着前提发挥。"
        '只输出 JSON：{"challenged": true|false}'
    )
    user = f"辩题：{motion_text}\n\n转录节选：\n{transcript[:3000]}"
    parsed = judge.ask_json(system, user)
    return bool((parsed or {}).get("challenged"))
