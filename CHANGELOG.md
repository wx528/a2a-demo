# Changelog

所有 notable 变更都会记录在这个文件里。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- Web 会议室新增「圆桌讨论模式（Roundtable）」：由 Moderator 主持，支持多轮自由讨论
- 新增 `moderator` 主持人 Agent：负责开场、控制发言顺序、总结讨论
- 每个 Agent 在圆桌模式下可以听到其他 Agent 的发言，并自主决定是否参与讨论（支持 PASS）
- 创建会议室时可通过前端下拉菜单选择「流水线模式」或「圆桌讨论模式」
- 圆桌讨论模式支持选择 1-10 轮，前端提供滑块控件
- 第一轮强制 Research、Writing Agent 发言，确保圆桌讨论有足够基础观点

### Changed

- 保留原有「流水线模式（Pipeline）」，作为默认模式继续可用
- 优化上下文长度控制，避免长讨论超出 LLM 上下文限制
- 优化圆桌讨论流程：移除主持人对每个 Agent 的单独决策调用，改为 Agent 自我判断是否 PASS，减少约 50% LLM 调用
- 限制圆桌模式下单次 Agent 发言长度，降低多轮讨论耗时和上下文膨胀

## [0.1.0] - 2026-06-15

### Added

- 初始版本发布
- 实现基于 A2A 协议的 Agent Swarm 架构
- 添加 `research-agent`：研究型 Agent，对主题生成摘要
- 添加 `writing-agent`：写作型 Agent，基于摘要生成 Markdown 文章
- 添加 `orchestrator`：编排器，串联多个 Agent 完成任务
- 添加通用 LLM 客户端，支持 OpenAI 兼容 API（OpenAI、DeepSeek、SiliconFlow、Ollama 等）
- 使用 `uv` 进行 Python 依赖管理
- 添加 Docker Compose 部署支持
- 添加 `.env.example` 环境变量示例
- 添加 Web 会议室演示界面（FastAPI + React + SSE）
- Web 会议室中集成 5 个 Agent：Research、Writing、Review、Code、Summary
- 支持 Agent 之间共享完整会议上下文
- 添加 `README.md` 项目文档
- 添加 `CHANGELOG.md`

[Unreleased]: https://github.com/scott/a2a/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/scott/a2a/releases/tag/v0.1.0
