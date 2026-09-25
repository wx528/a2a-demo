"""辩论质量评测 CLI：辩题集 x 真实辩论 -> 指标 + judge -> JSON/MD 报告。"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import httpx

from debate.personas import PERSONAS
from debate.run_debate import run_debate
from evals.quality import metrics
from evals.quality.judge import (
    Judge,
    judge_claim_support,
    judge_persona_adherence,
    judge_premise_challenge,
)
from evals.quality.motions import get_motions

DEFAULT_AGENT_URL = "http://localhost:8003"
NAME_TO_STYLE = {p["name"]: p["style"] for p in PERSONAS.values()}


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _persona_name(header: str) -> str:
    # "第 1 手 · 苏格拉底（正方）" -> "苏格拉底"
    name = header.split("·")[-1]
    return re.sub(r"（.*?）", "", name).strip()


def eval_motion(motion: dict, args, judge: Judge) -> dict:
    transcript = run_debate(motion["text"], args.pro, args.con, args.rounds, args.agent_url)
    turns = metrics.parse_turns(transcript)
    cov, cited, declared = metrics.citation_coverage(turns)
    urls = sorted({u for t in turns for u in metrics.turn_citations(t["text"])})
    liveness = asyncio.run(metrics.check_liveness(urls))
    lrate, dead = metrics.liveness_rate(liveness)

    row = {
        "id": motion["id"],
        "motion": motion["text"],
        "trap": bool(motion.get("trap")),
        "turns": len(turns),
        "citation_coverage": round(cov, 3),
        "cited_turns": cited,
        "declared_turns": declared,
        "link_liveness": round(lrate, 3),
        "dead_links": dead,
        "transcript_chars": len(transcript),
    }

    if judge.available:
        verdicts: List[dict] = []
        for t in turns:
            cites = metrics.turn_citations(t["text"])
            if not cites:
                continue
            sources = [
                {"url": u, "snippet": liveness.get(u, {}).get("content", "")} for u in cites
            ]
            verdicts.extend(judge_claim_support(t["text"], sources, judge))
        supported = [v for v in verdicts if v.get("verdict") == "supported"]
        row["claim_support_rate"] = round(len(supported) / len(verdicts), 3) if verdicts else None
        row["claim_verdicts"] = verdicts

        scores = []
        for t in turns:
            style = NAME_TO_STYLE.get(_persona_name(t["header"]), "")
            score = judge_persona_adherence(style, t["text"], judge)
            if score > 0:
                scores.append(score)
        row["persona_adherence"] = round(sum(scores) / len(scores), 2) if scores else None

    if motion.get("trap"):
        challenged = (
            judge_premise_challenge(motion["text"], transcript, judge)
            if judge.available else False
        )
        row["trap_honesty"] = bool(metrics.trap_honesty(transcript) or challenged)

    return row


def aggregate(rows: List[dict]) -> dict:
    def mean(key: str) -> Optional[float]:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    traps = [r for r in rows if r.get("trap")]
    return {
        "motions": len(rows),
        "citation_coverage": mean("citation_coverage"),
        "link_liveness": mean("link_liveness"),
        "claim_support_rate": mean("claim_support_rate"),
        "persona_adherence": mean("persona_adherence"),
        "trap_pass_rate": (
            round(sum(1 for r in traps if r.get("trap_honesty")) / len(traps), 3)
            if traps else None
        ),
    }


def build_markdown(meta: dict, summary: dict, rows: List[dict]) -> str:
    judged = "self-judged" if meta.get("self_judged") else "independent judge"
    lines = [
        "# 辩论质量评测报告",
        "",
        f"- 时间：{meta.get('date')}",
        f"- git：{meta.get('git')}",
        f"- 模型：{meta.get('llm_model')}　裁判：{meta.get('judge_model')}（{judged}）",
        "",
        "## 汇总",
        "",
        "| 指标 | 值 |",
        "|------|-----|",
    ]
    for key in ("motions", "citation_coverage", "link_liveness",
                "claim_support_rate", "persona_adherence", "trap_pass_rate"):
        lines.append(f"| {key} | {summary.get(key)} |")
    lines += ["", "## 逐题", "",
              "| id | 辩题 | 陷阱 | 轮次 | 引用覆盖 | 链接存活 | 论断支持 | 人格 | 陷阱通过 |",
              "|----|------|------|------|----------|----------|----------|------|----------|"]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['motion'][:24]} | {'是' if r.get('trap') else ''} "
            f"| {r.get('turns')} | {r.get('citation_coverage')} | {r.get('link_liveness')} "
            f"| {r.get('claim_support_rate')} | {r.get('persona_adherence')} | {r.get('trap_honesty', '')} |"
        )
    dead_total = sum(len(r.get("dead_links", [])) for r in rows)
    if dead_total:
        lines += ["", f"死链共 {dead_total} 条（详见 JSON 报告 dead_links 字段）"]
    return "\n".join(lines) + "\n"


def wait_for_ready(url: str, timeout: float = 60.0) -> bool:
    start = time.time()
    with httpx.Client(trust_env=False, timeout=3) as c:
        while time.time() - start < timeout:
            try:
                if c.get(f"{url}/").status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="辩论质量评测")
    parser.add_argument("--limit", type=int, default=None, help="只评前 N 题")
    parser.add_argument("--motions", default=None, help="逗号分隔的辩题 id")
    parser.add_argument("--pro", default="socrates")
    parser.add_argument("--con", default="hume")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL)
    parser.add_argument("--spawn", action="store_true", help="自动拉起本地 debate-agent 子进程")
    parser.add_argument("--out", default=None, help="报告目录（默认 evals/reports/）")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if args.motions:
        motions = get_motions([m.strip() for m in args.motions.split(",") if m.strip()])
    else:
        motions = get_motions()
        if args.limit:
            motions = motions[: args.limit]

    proc = None
    if args.spawn:
        proc = subprocess.Popen(
            [sys.executable, "debate_agent/main.py"],
            cwd=repo_root, env=os.environ.copy(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not wait_for_ready(args.agent_url):
            print(f"error: debate-agent not ready at {args.agent_url}", file=sys.stderr)
            proc.terminate()
            return 1

    judge = Judge()
    if not judge.available:
        print("warning: judge unavailable (no keys) — deterministic metrics only", file=sys.stderr)

    started = time.time()
    rows = []
    try:
        for i, motion in enumerate(motions, 1):
            print(f"[{i}/{len(motions)}] {motion['id']}: {motion['text']}", file=sys.stderr)
            rows.append(eval_motion(motion, args, judge))
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    summary = aggregate(rows)
    meta = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git": git_sha(),
        "llm_model": os.getenv("LLM_MODEL", ""),
        "judge_model": judge.model,
        "self_judged": judge.self_judged,
        "duration_s": round(time.time() - started, 1),
    }
    md = build_markdown(meta, summary, rows)
    print(md)

    out_dir = args.out or os.path.join(repo_root, "evals", "reports")
    os.makedirs(out_dir, exist_ok=True)
    stem = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{meta['git']}"
    with open(os.path.join(out_dir, f"{stem}.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "summary": summary, "rows": rows}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, f"{stem}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(f"reports written to {out_dir}/{stem}.{{json,md}}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
