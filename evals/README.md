# Evaluation

Two tiers. 简体中文说明见下。

## Tier 1 — A2A Conformance Suite (offline, free)

Deterministic spec-compliance checks against any live A2A agent:

```bash
uv run python research_agent/main.py &
uv run python evals/conformance/suite.py --url http://localhost:8001
```

11 checks (agent card, SendMessage v1, millisecond timestamps, legacy aliases,
GetTask, error format, terminal continuation rejection, multi-turn, context
seeding, ListTasks, streaming chunks). Exit 0 iff all non-skipped checks pass.
`--json PATH` writes a machine-readable report. Runs in CI on every push.

## Tier 2 — Debate Quality Evals (LLM-as-judge, costs money)

```bash
uv run python evals/quality/run_eval.py --spawn --limit 3
```

Metrics per motion: citation coverage, link liveness (real HTTP checks),
claim-support rate and persona adherence (judged), trap-motion honesty
(false-premise motions must be challenged or declared unsupported).

Judge configuration: set `JUDGE_API_KEY` / `JUDGE_BASE_URL` / `JUDGE_MODEL`
for an independent judge; without them the runner falls back to `LLM_*` and
stamps the report `self_judged: true`.

Reports land in `evals/reports/` (gitignored) as JSON + Markdown.
CI: GitHub Actions workflow `Eval` (manual dispatch only).

## 中文说明

- 一致性套件：离线免费，对任意 A2A agent 打分（11 项检查），CI 每次 push 自动跑
- 质量评测：需要 LLM key，引用覆盖/链接存活为确定性指标，论断支持率与人格保持度由裁判模型打分；
  陷阱题考察"声明无据"而非配合幻觉。独立裁判用 `JUDGE_*` 环境变量，未配置回退 `LLM_*` 并标注自评
