# A2A Agent Swarm 示例

[![CI](https://github.com/wx528/a2a-demo/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/wx528/a2a-demo/actions/workflows/ci.yml)
[![LLM Smoke](https://github.com/wx528/a2a-demo/actions/workflows/llm-smoke.yml/badge.svg?branch=main)](https://github.com/wx528/a2a-demo/actions/workflows/llm-smoke.yml)

[English](README.md) | **简体中文**

这是一个最小可运行的 **A2A (Agent-to-Agent)** 示例，包含：

- `research-agent`：研究型 agent，接收主题返回摘要
- `writing-agent`：写作型 agent，基于摘要生成 Markdown 文章
- `orchestrator`：编排器，动态发现 agent 并串联 research → writing
- `web`：会议室演示（FastAPI + React + SSE），可视化 agent 协作过程

所有 agent 都通过 **JSON-RPC 2.0** 暴露 A2A 协议接口（对齐 [A2A v1.0 规范](https://a2a-protocol.org/latest/specification/)）：
- `GET /.well-known/agent-card.json`：Agent Card（发现，旧路径 `agent.json` 保留为兼容别名）
- `POST /rpc`：JSON-RPC 入口，支持 `SendMessage`、`GetTask`、`CancelTask`、`ListTasks`（旧名 `tasks/send` 等保留为兼容别名）
- `POST /rpc/stream`：SSE 流式入口，支持 `SendStreamingMessage`、`SubscribeToTask`

> 2026-09 更新：数据模型、方法名、枚举值、错误格式与时间戳精度已对齐现行 v1.0.0 规范（PascalCase 方法名、`TASK_STATE_*` / `ROLE_*` 枚举、`google.rpc.ErrorInfo` 错误、毫秒时间戳）。任务失败自动落 `TASK_STATE_FAILED`；支持多轮会话：消息带 `taskId` 续聊既有任务，带 `contextId` 新建任务并继承上下文历史。内置真流式输出与 SQLite 任务持久化。

---

## 目录结构

```
~/a2a/
├── shared/                 # A2A 数据模型 + JSON-RPC 服务端/客户端 + LLM 客户端 + 任务存储
│   ├── models.py           # A2A v1.0 数据模型（Pydantic v2，camelCase 别名）
│   ├── a2a_server.py       # 可复用的 JSON-RPC agent 服务端（任务、流式）
│   ├── a2a_client.py       # 极简 A2A JSON-RPC 客户端
│   ├── llm_client.py       # OpenAI 兼容 LLM 客户端（阻塞 + 流式）
│   └── task_store.py       # SQLite 任务持久化（TASK_DB 启用）
├── research_agent/         # 研究 agent
│   ├── main.py
│   └── Dockerfile
├── writing_agent/          # 写作 agent
│   ├── main.py
│   └── Dockerfile
├── debate_agent/           # 人格辩论 agent
│   ├── main.py
│   └── Dockerfile
├── orchestrator/           # 编排器（动态发现）
│   ├── main.py
│   ├── registry.py         # AgentRegistry：基于 Agent Card 的发现注册表
│   └── Dockerfile
├── debate/                 # 辩论 Demo CLI 编排器
│   ├── personas.py         # 人格库（苏格拉底 / 休谟 / 康德 ……）
│   └── run_debate.py       # 多轮对抗辩论 + 裁判判定
├── evals/                  # 一致性套件 + 辩论质量评测
│   ├── conformance/        # A2A 协议合规检查（离线）
│   ├── quality/            # 辩题集、指标、LLM-as-judge、评测 runner
│   └── README.md           # 评测指南（两个层级）
├── web/                    # 会议室 Web 演示
│   ├── main.py
│   ├── db.py               # 会议 SQLite 持久化
│   ├── static/index.html
│   └── Dockerfile
├── .github/workflows/      # CI + LLM 冒烟测试
├── docker-compose.yml
├── pyproject.toml          # uv 依赖管理
├── uv.lock                 # uv 锁定文件
├── .env.example
├── README.md
├── README.zh-CN.md
└── CHANGELOG.md
```

---

## LLM 配置（可选但推荐）

Agent 内部优先调用 LLM 生成内容。支持所有 **OpenAI 兼容 API**：

- OpenAI
- DeepSeek
- SiliconFlow
- 本地 Ollama / vLLM

通过环境变量配置：

```bash
export LLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
```

**不配置 LLM 也能跑**，会自动回退到本地模板数据。

### 常见模型配置示例

或者复制示例文件：

```bash
cp .env.example .env
# 编辑 .env 填入你的 API Key 和模型配置
vim .env
```

**DeepSeek：**
```bash
export LLM_API_KEY="sk-..."
export LLM_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"
```

**SiliconFlow：**
```bash
export LLM_API_KEY="sk-..."
export LLM_BASE_URL="https://api.siliconflow.cn/v1"
export LLM_MODEL="Qwen/Qwen2.5-7B-Instruct"
```

**本地 Ollama：**
```bash
export LLM_BASE_URL="http://host.docker.internal:11434/v1"
export LLM_MODEL="llama3.1"
# Ollama 通常不需要 API Key
```

---

## 快速开始

### 1. 使用 Docker Compose（推荐）

```bash
cd ~/a2a
docker compose up --build
```

启动后：
- Orchestrator: http://localhost:8000
- Research Agent: http://localhost:8001
- Writing Agent: http://localhost:8002

### 2. 测试 Agent Card

```bash
curl http://localhost:8001/.well-known/agent-card.json
curl http://localhost:8002/.well-known/agent-card.json
```

### 3. 测试完整工作流

```bash
curl -X POST http://localhost:8000/create-article \
  -H "Content-Type: application/json" \
  -d '{"topic": "kubernetes"}'
```

### 4. 直接调用单个 Agent（通过 Orchestrator）

```bash
# 直接调用 research agent（支持短名 / card 名称 / skill id）
curl -X POST http://localhost:8000/direct/research \
  -H "Content-Type: application/json" \
  -d '{"topic": "a2a"}'

# 直接调用 writing agent
curl -X POST http://localhost:8000/direct/writing \
  -H "Content-Type: application/json" \
  -d '{"topic": "A2A 协议的核心概念"}'
```

### 5. 直接调用 A2A JSON-RPC 端点

```bash
# research-agent: 发送任务（阻塞返回）
curl -X POST http://localhost:8001/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-001",
        "role": "ROLE_USER",
        "parts": [{"text": "kubernetes"}]
      }
    }
  }'

# 查询任务状态
curl -X POST http://localhost:8001/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "GetTask",
    "params": {"id": "TASK_ID_HERE"}
  }'

# 流式发送任务（SSE，token 级增量）
curl -N -X POST http://localhost:8001/rpc/stream \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "SendStreamingMessage",
    "params": {
      "message": {
        "messageId": "msg-002",
        "role": "ROLE_USER",
        "parts": [{"text": "a2a"}]
      }
    }
  }'
```

---

## 本地开发（不用 Docker）

使用 [uv](https://docs.astral.sh/uv/) 管理依赖：

```bash
cd ~/a2a

# 安装依赖（根据 uv.lock）
uv sync

# 启动 research agent
uv run python research_agent/main.py &

# 启动 writing agent
uv run python writing_agent/main.py &

# 启动 orchestrator
uv run python orchestrator/main.py &
```

注意本地运行时，需要设置这些环境变量：

```bash
export RESEARCH_AGENT_URL=http://localhost:8001
export WRITING_AGENT_URL=http://localhost:8002

# 可选：配置 LLM
export LLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
```

---

## 测试与 CI

| 层级 | 文件 | 说明 |
|------|------|------|
| 单元测试 | `test_a2a.py` / `test_registry.py` / `test_task_store.py` | 协议行为、注册表、持久化，无需起服务 |
| 端到端 | `test_e2e.py` | 起真实进程验证 agent + orchestrator 工作流 |
| Web 集成 | `test_web.py` | 会议室 SSE 全链路 |
| LLM 冒烟 | `test_llm_smoke.py` | 真实 LLM 链路（默认 DeepSeek），无 key 自动跳过 |

CI（GitHub Actions）：
- **CI**（每次 push/PR）：ruff + 全部离线测试，不消耗 LLM 额度
- **LLM Smoke**（push main / 手动触发）：用真实 key 验证非回退输出与真流式；需在仓库 Secrets 配置 `LLM_API_KEY`（DeepSeek），可用 Variables 覆盖 `LLM_BASE_URL`/`LLM_MODEL`（默认 `https://api.deepseek.com/v1` / `deepseek-chat`）

---

## Web 会议室演示

项目包含一个可视化会议室界面，可以直观看到多个 Agent 的协作过程。

### 启动

Web 服务已经包含在 docker compose 中，启动后会自动运行：

```bash
cd ~/a2a
docker compose up -d
```

### 访问

浏览器打开：http://localhost:8080

### 使用流程

1. 输入会议主题（例如：`Kubernetes`、`A2A protocol`）
2. 创建会议室
3. 观察 Research Agent 和 Writing Agent 依次发言
4. 你可以在底部输入框继续提问，Agent 会继续响应

### 技术实现

- **后端**：FastAPI + SSE（Server-Sent Events）实时推送
- **前端**：React（CDN 版）+ Tailwind CSS
- **A2A 调用**：会议室中的每个 Agent 发言都通过 `POST /rpc` 发送 `SendMessage` 给 `research-agent` 或 `writing-agent`
- **实时状态**：Agent 会显示"思考中"、"发言中"、"等待中"等状态

---

## 人格辩论 Demo

人格化角色（哲学家与现代原型）之间的事实性辩论。每一轮：`debate-agent`
先检索网络资料，再带内联引用进行论证；缺少资料时会明说，绝不编造。

```bash
# 启动辩论 agent（或 docker compose up）
uv run python debate_agent/main.py &

uv run python debate/run_debate.py "AI 会取代大多数工作吗" \
    --pro socrates --con hume --rounds 2
```

可选人格：`socrates`、`hume`、`kant`、`nietzsche`、
`skeptic_engineer`、`vc`。搜索默认走 DuckDuckGo，开箱即用；
设置 `SEARCH_PROVIDER=tavily` + `SEARCH_API_KEY` 可获得更高质量的结果。

转录示例（节选）：

```markdown
## 第 1 手 · 苏格拉底（正方）

我们首先要问：所谓"取代"，究竟是指任务被自动化，还是人的价值被消除？
历史数据显示，ATM 普及后美国银行柜员岗位不降反升 [来源1](https://www.aei.org/...)。
但请注意：这是相关性陈述，因果推断属于推演……

## 裁判总结 · 裁判

正方最强论据来自就业结构数据 [来源1](https://www.aei.org/...)；
反方对"任务替代 ≠ 岗位替代"的区分没有任何来源直接支撑，属于未查证推演……
```

---

## 评测

两个层级，详见 [evals/README.md](evals/README.md)：

- **一致性套件**（离线免费）：11 项 A2A 协议合规检查，可对任意在线 agent 打分；CI 每次 push 自动运行
- **辩论质量评测**（LLM-as-judge，手动触发）：15 题辩题集上的引用覆盖率、链接存活率、
  论断支持率、人格保持度与陷阱题诚实度，输出 JSON + Markdown 报告

---

## 扩展方向

1. **接入真实 LLM**：配置 `LLM_API_KEY` 等环境变量即可启用
2. **增加 agent**：复制现有 agent 改 `process_task`，把地址加进 `AGENT_URLS` 即被发现（也可运行时 `POST /agents/refresh`）
3. **鉴权与安全**：Agent Card 声明 securitySchemes、校验 `A2A-Version`、push notification
4. **协作式取消**：CancelTask 会把任务标记为 CANCELED，但正在执行的 worker（阻塞或流式）会继续跑到结束并消耗 LLM token——迟到的写入会被终态守卫丢弃
5. **任务分页**：`ListTasks` 换成游标分页（`nextPageToken`）
6. **错误重试**：在 orchestrator 里加重试和超时控制
7. **K8s 部署**：把每个 service 改成 Deployment + Service

---

## 参考

- [A2A 协议规范](https://a2a-protocol.org/latest/specification/)
- [A2A Protocol (GitHub)](https://github.com/a2aproject/A2A)
