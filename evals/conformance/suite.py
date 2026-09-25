"""A2A 一致性套件 CLI：对任意 A2A agent 逐项打分出报告。"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from evals.conformance.checks import run_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="A2A conformance suite")
    parser.add_argument("--url", required=True, help="agent 基础 URL，如 http://localhost:8001")
    parser.add_argument("--streaming", action="store_true",
                        help="强制执行流式检查（即使 card 声明 streaming=false）")
    parser.add_argument("--json", default=None, help="写 JSON 报告到文件")
    args = parser.parse_args()

    results = asyncio.run(run_suite(args.url, force_streaming=args.streaming))
    width = max(len(r.name) for r in results) + 2
    for r in results:
        print(f"{r.name:<{width}} {r.status:<5} {r.detail}")

    evaluated = [r for r in results if r.status != "SKIP"]
    passed = sum(1 for r in evaluated if r.status == "PASS")
    skipped = len(results) - len(evaluated)
    suffix = f" ({skipped} skipped)" if skipped else ""
    print(f"\n{passed}/{len(evaluated)} passed{suffix}")

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(
                {"url": args.url, "results": [asdict(r) for r in results],
                 "passed": passed, "evaluated": len(evaluated)},
                f, ensure_ascii=False, indent=2,
            )
        print(f"json report: {args.json}")

    return 0 if evaluated and passed == len(evaluated) else 1


if __name__ == "__main__":
    sys.exit(main())
