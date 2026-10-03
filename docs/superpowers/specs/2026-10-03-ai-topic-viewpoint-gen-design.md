# AI 议题生成与观点预览 设计文档

日期：2026-10-03
状态：已与用户确认

## 背景与目标

创建会议时议题靠手输。新增 LLM 辅助：自动生成候选议题供点选；辩论模式下可预览双方开篇立论。展示「AI 自动化」的产品感。

## 已确认决策

1. 调用链路：web 后端直连 LLM（`shared.llm_client.call_llm`，`.env` 已在 web 进程加载），不走 agent。
2. 观点预览：按钮触发（非自动），仅辩论模式显示。

## 后端（2 个 additive 端点）

- `POST /api/topics/suggest`，body `{count?: int = 3}` → 1 次 `call_llm`，提示词要求输出 JSON 字符串数组（中文、适合辩论/圆桌讨论的议题）→ 健壮解析（截取首个 `[...]` 片段 `json.loads`，失败退化为按行分割）→ 返回 `{"topics": string[]}`。LLM 失败/空 → HTTP 502 `{"detail": "AI 生成失败，请稍后重试"}`。
- `POST /api/viewpoints/preview`，body `{topic: str, pro_persona: str, con_persona: str}` → 校验辩题非空与人格存在（查 `PERSONAS`）→ `asyncio.gather` 并行 2 次 `call_llm`（system 用 `build_system_prompt()` 同源的简短中立主持指令 + 各自人格 `style`，user 为「就辩题 X 给出你方开篇立论，120 字以内」，`max_tokens=350`）→ 返回 `{"pro": str, "con": str}`。单项失败该侧返回「（生成失败，请重试）」。辩题空 → 422。
- 新文件：`web/generators.py`（提示词组装、JSON 解析、两个异步函数），`main.py` 只挂路由。`call_llm` 是同步函数 → 用 `asyncio.to_thread` 包装避免阻塞事件循环。

## 前端（CreateMeetingDialog 内）

- 主题 Input 相对定位，右侧内嵌 ✨ 按钮（Sparkles 图标，「AI 生成」title）。点击 → `api.suggestTopics()` → loading（按钮转圈）→ Input 下方渲染候选 chip 列表（`rounded-full border` 小按钮），点击 chip 填入主题框；再点生成替换。失败 toast。
- 辩论模式右栏「预览双方开篇立论」Button（`!topic.trim()` 或生成中禁用）→ 两个并排小卡片：正方（primary 描边 + 「正方 · {人格名}」标签）/ 反方（assist 描边 + 「反方 · {人格名}」）；loading 时卡片内 Skeleton 三行；结果 `whitespace-pre-wrap text-xs`。再次点击可重新生成。
- `lib/api.ts` 加 `suggestTopics(count?)` 与 `previewViewpoints({topic, pro_persona, con_persona})`。

## 不变

现有 API/SSE、hooks、其它页面；`inquiry_enabled` 等逻辑不动。

## 错误处理

前端 toast 中文错误；预览按钮 LLM 失败时卡片内显示「（生成失败，请重试）」而非整体报错。

## 验证

- `ruff` + 现有 pytest 全绿；`npm run build`/`lint` 通过。
- Playwright 冒烟：打开弹窗 → 生成议题 → 出现 ≥1 个 chip → 点选填入 → 切辩论 → 预览 → 两卡片非空。真实 LLM 调用，网络失败时该冒烟项标 SKIPPED 而非 FAIL。

## 明确不做（YAGNI）

- 圆桌/流水线的观点预览；议题生成的领域参数 UI；流式输出；候选议题的历史缓存。
