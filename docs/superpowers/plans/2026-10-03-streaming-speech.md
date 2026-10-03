# 流式发言 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** 发言从整段等待改为逐 token 流式渲染，打通 agent `/rpc/stream` → web SSE → 前端增量气泡。

**Architecture:** `a2a_client.stream_deltas` 增量解析 → web `message_delta`/`message_abort` SSE 事件 → 前端占位气泡追加 + `message` 幂等替换。

## Global Constraints

- SSE 协议仅 additive（`message_delta`/`message_abort` 新事件）；agent 端零改动；DB 只落最终消息。
- `<think>` 推理前缀不得进入气泡。
- 每 Task `npm run build`/`lint`、触碰后端跑 `ruff`，通过后 commit。

### Task 1: a2a_client.stream_deltas

**Files:** Modify `shared/a2a_client.py`

**Interfaces:**
- Produces: `async def stream_deltas(self, text: str) -> AsyncIterator[str]`（增量 yield 文本；`artifact_update.artifact.parts[].text` 拼接；status completed/failed 结束；异常向上抛）。

- [ ] 实现（参照 `stream_send`，逐行 `aiter_lines` 解析 `data:` JSON；`httpx.AsyncClient(timeout=120, trust_env=False)`）
- [ ] `ruff check .`；commit `feat(shared): incremental a2a stream deltas client`

### Task 2: web 流式化

**Files:** Modify `web/main.py`

**Interfaces:**
- Consumes: Task 1 `stream_deltas`；`call_debate_agent_stream` 走 `DEBATE_AGENT_URL`。
- Produces: SSE 事件 `message_delta {participant_id, delta}`、`message_abort {participant_id}`；`message` 事件语义不变。

- [ ] `_ThinkFilter` 类 + `call_agent_stream`/`call_debate_agent_stream` + 兜底 `call_agent`；重写 `run_agent_step`、`_run_debate_step`、`_run_classic_step` PASS 路径（事件顺序：thinking → delta* → speaking → message → idle；PASS：thinking → delta* → abort → system PASS）
- [ ] `ruff check .`；`pytest test_web_turns.py test_web_scheduler.py -q`；`test_web.py`；commit `feat(web): stream agent speech through sse`

### Task 3: 前端增量渲染

**Files:** Modify `src/hooks/useMeetingRoom.ts`、`src/components/MessageBubble.tsx`、`src/components/MessageList.tsx`

**Interfaces:**
- Consumes: `message_delta`/`message_abort` 事件。
- Produces: 流式占位消息（id `streaming-{participant_id}`）；气泡光标；滚动跟随内容增长。

- [ ] applyTurnEvent 三事件处理；MessageBubble 光标；MessageList 滚动依赖
- [ ] build + lint；commit `feat(web): incremental message rendering with cursor`

### Task 4: 验证（控制器）

- [ ] 全量回归：ruff/pytest/build/lint/test_web
- [ ] Playwright：真实 LLM 下气泡两次采样长度递增；辩论/圆桌/PASS/插话/删除冒烟；截图
- [ ] 修复（如有）+ commit `fix(web): streaming acceptance fixes`
