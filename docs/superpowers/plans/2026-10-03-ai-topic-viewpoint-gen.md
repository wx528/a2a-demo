# AI 议题生成与观点预览 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** 创建会议弹窗支持 LLM 生成候选议题（点选填入）与辩论双方开篇立论预览（按钮触发）。

**Architecture:** `web/generators.py` 封装提示词/解析/异步 LLM 调用；`main.py` 挂 2 个路由；弹窗加生成按钮 + 候选 chips + 预览卡片。

**Tech Stack:** 既有栈，无新依赖。

## Global Constraints

- API additive-only；LLM 同步调用必须 `asyncio.to_thread` 包装。
- 所有失败路径不 500 裸奔：suggest 失败 502；preview 单侧失败返回占位文案。
- 中文文案；`npm run build`/`lint`/`ruff` 每任务通过后 commit。

### Task 1: 后端 generators + 路由

**Files:** Create `web/generators.py`；Modify `web/main.py`（import + 2 路由）

**Interfaces:**
- Produces: `POST /api/topics/suggest` → `{"topics": [str]}`；`POST /api/viewpoints/preview` → `{"pro": str, "con": str}`；内部 `async def suggest_topics(count: int) -> list[str]`、`async def preview_viewpoints(topic: str, pro_id: str, con_id: str) -> tuple[str, str]`。

- [ ] generators.py：`_extract_json_array(text) -> list[str]`（找首个 `[` 到末个 `]`，json.loads，退化按行去空）；`suggest_topics(count)`（system: 中文会议主持人，输出 JSON 数组；user: 生成 count 个适合 AI Agent 辩论或圆桌讨论的中文议题，风格多样；`asyncio.to_thread(call_llm, sys, usr, max_tokens=500)`；解析失败抛 ValueError）；`preview_viewpoints(topic, pro_id, con_id)`（并行两路 to_thread，system: `f"你是{ stance }辩手，风格：{PERSONAS[pid]['style']}。直接输出论点，不要思考过程。"`，user: `f"辩题：{topic}\n请给出你方开篇立论，120 字以内。"`，max_tokens=350；单路异常返回「（生成失败，请重试）」）。
- [ ] main.py：`import generators`；两个路由（suggest try/except → HTTPException 502；preview 校验 topic/人格 → 422）。
- [ ] `ruff check .`；`pytest test_web_turns.py test_web_scheduler.py -q`；commit `feat(web): ai topic suggestion and viewpoint preview endpoints`

### Task 2: 前端弹窗集成

**Files:** Modify `src/lib/api.ts`、`src/components/CreateMeetingDialog.tsx`

**Interfaces:**
- Consumes: Task 1 两端点。
- Produces: 弹窗内状态 `suggesting/suggestions/previewing/preview: {pro,con} | null`。

- [ ] api.ts：`suggestTopics(count = 3): Promise<{ topics: string[] }>`、`previewViewpoints(body): Promise<{ pro: string; con: string }>`（POST，request 已有）。
- [ ] Dialog：主题 Input 包 relative 容器 + 内嵌 Sparkles 按钮（suggesting 时 Loader2 转圈）；候选 chips（`suggestions.map` 圆角小按钮，点击 setTopic）；辩论右栏「预览双方开篇立论」按钮（disabled: !topic.trim() || previewing）+ 双卡片（正方 primary 边/反方 assist 边，标签「正方 · 名」「反方 · 名」，previewing 时三行 Skeleton，单侧「（生成失败，请重试）」直接展示文本）。
- [ ] build + lint；commit `feat(web): topic suggestion chips and viewpoint preview in create dialog`

### Task 3: 验证（控制器）

- [ ] ruff/pytest/build/lint 全绿；重启 web；Playwright 冒烟（生成 chip → 点选 → 预览卡片非空；LLM 网络失败该项记 SKIPPED）；截图确认样式。
- [ ] 修复（如有）+ commit `fix(web): topic gen acceptance fixes`
