# 流式发言 设计文档

日期：2026-10-03
状态：已与用户确认

## 背景

点「继续」后需等待 LLM 完整生成才出整段消息（30-60s 静默）。agent 端 `/rpc/stream` 已逐 token 推 `artifact_update` SSE 事件（三 agent 均注册 `stream_response`），但 web 层 `stream_send` 缓冲式消费丢弃了增量。目标：发言逐字流式渲染。

## 设计

### a2a_client（新增方法）
`stream_deltas(text) -> AsyncIterator[str]`：与 `stream_send` 相同请求（`SendStreamingMessage` → `/rpc/stream`），但逐行解析 SSE：`artifact_update.artifact.parts[].text` 逐个 yield；忽略 status/初始 task 事件；completed/failed 状态到达即结束。原 `stream_send` 保留。

### web/main.py
- 新增 `call_agent_stream(agent_key, input_text) -> AsyncIterator[str]`（role_hint 拼接同 `call_agent`）与 `call_debate_agent_stream(text)`。
- 新增累积过滤器 `_ThinkFilter`：累计到 `</think>` 后才放行增量（若从未出现则全部放行）。
- `run_agent_step` 重写：status thinking → 迭代流，首个增量即对外发 `message_delta`（事件载荷 `{participant_id, delta}`）→ 结束后 `add_message`（完整文本）→ `message` 事件 → idle。异常兜底：若累计了部分文本则用它落库；全程无增量则退化为 `call_agent` 旧路径。
- `_run_classic_step` 圆桌 PASS 路径：改为流式；结束后若文本 strip 后大写以 PASS 开头 → 发 `message_abort`（清占位）+ 现有 system PASS 提示；否则 `status speaking` → `message` → `idle`。
- `_run_debate_step`：同 `run_agent_step` 流式化（judge 同）。
- SSE 协议新增事件：`message_delta`、`message_abort`（additive）。DB 仍只写最终消息。

### 前端
- `applyTurnEvent`：
  - `message_delta`：找到/创建 `id=streaming-{participant_id}` 占位消息（participant_name/avatar 从 participants 取，type="message"），content 追加 delta。
  - `message`：先移除同 participant 的 `streaming-*` 占位，再追加正式消息（现有逻辑 + 移除步骤）。
  - `message_abort`：移除该 participant 的 `streaming-*` 占位。
- `MessageBubble`：`msg.id.startsWith("streaming-")` 时内容后加闪烁光标（`animate-pulse` 的 ▌span）。
- `MessageList`：自动滚动 effect 依赖追加最后一条消息的 content 长度。

## 错误处理

- agent 流中断/异常：web 端以已累计文本落库（无则 `call_agent` 全量兜底），前端占位由最终 `message`/`message_abort` 收敛；最坏情况占位滞留由下次 `message` 清除。
- `<think>` 过滤器保证推理前缀不进气泡。

## 验证

ruff / pytest（web 相关）/ build / lint / test_web 全绿；真实 LLM E2E：气泡两次采样文本长度递增（证明流式）、辩论、圆桌、PASS、插话、删除全冒烟。

## 不做

Agent 端协议改动；思考过程（<think> 内容）展示；逐字动画特效（直接增量渲染）。
