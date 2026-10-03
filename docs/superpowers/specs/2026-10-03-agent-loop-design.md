# Agent 内循环（检索→起草→自审→修订） 设计文档

日期：2026-10-03
状态：已与用户确认

## 背景

当前每个 Agent 每轮 = 单次 LLM 调用（上下文快照 + 单向输出），无草稿、无自审、无检索（辩论除外的一次性 RAG）。目标：给内容型 Agent 加内部工作循环，提升发言质量，同时保持流式观感（观众能看到阶段进度而非干等）。

## 已确认决策

- 协议复用：中间阶段包 `<think>`（web 现有过滤器自动隐藏）；新增 `[PHASE] xxx` 标记行由 web 拦截转为 additive SSE 事件 `agent_phase`（参与者胶囊显示阶段文案）。
- 接入范围：research（新增检索能力）、writing（起草+自审）、debate（检索→立论→预演→定稿）；review/code/summary 保持单次。
- 失败降级：任何中间阶段失败 → 跳过该阶段直出（不劣于现状）。

## 设计

### shared/agent_loop.py（新）
`agentic_stream(system, user, search_context="", critique=True, max_tokens=2000) -> Iterator[str]`
1. `[PHASE] 整理思路`
2. `<think>` 内流式起草（system+草稿指示，user+search_context）
3. `[PHASE] 自我审视` → `<think>` 内一次 call_llm（非流式）：以严格编辑身份列 3 条改进点
4. `[PHASE] 输出最终发言` → 流式输出修订稿（system + user + 草稿 + 编辑意见）
- 每个 `[PHASE]` 标记整行一次性 yield（保证 web 端原子拦截）
- 中间 LLM 异常吞掉产出空块；最终阶段失败则整体产出空（调用方已有 fallback）

### Agent 端接入
- research：`stream_response` 重写——`web_search(user[:80], 4)` 检索（新能力）→ 格式化为 search_context → `agentic_stream(DEFAULT_SYSTEM_PROMPT, user_text, search_context)`；检索异常 → 空 context 继续
- writing：同上（无检索）
- debate：保留 `gather_sources`；`agentic_stream(build_system_prompt(), compose_user_prompt(...), search_context=_format_sources(sources))`
- 非流式 `process_task` 路径保持不变

### web/main.py（三个流式循环处）
- delta 以 `[PHASE]` 开头 → 发 `agent_phase {participant_id, phase}`，不入 bubble、不入累计文本
- 最终 `result` 组装后 `re.sub(r"\[PHASE\][^\n]*", "", ...)` 清洗（防泄漏）
- 圆桌 PASS 路径同样清洗后再判定

### 前端
- types：Participant 加 `phase?: string`
- applyTurnEvent：`agent_phase` → 设置 participant.phase；`status idle` / `message` 到达时清空
- ParticipantBar：thinking 状态显示 `phase ?? "思考中"`（保留三点动画）

## 错误处理
见各「失败降级」；搜索失败无资料继续；`<think>` 无闭合时不泄漏（web 过滤器 final_text 已处理）。

## 验证
ruff/pytest/build/lint/test_web 全绿；真实 LLM 三模式冒烟：阶段标签依序切换、最终消息无 [PHASE] 泄漏、质量目测提升。

## 不做
多轮批判（只 1 轮自审）；跨会议记忆；agent 状态页 UI。
