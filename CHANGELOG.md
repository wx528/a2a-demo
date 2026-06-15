# Changelog

所有 notable 变更都会记录在这个文件里。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

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
