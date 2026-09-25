# A2A Agent Swarm 示例

这是一个最小可运行的 **A2A (Agent-to-Agent)** 示例，包含：

- `research-agent`：研究型 agent，接收主题返回摘要
- `writing-agent`：写作型 agent，基于摘要生成 Markdown 文章
- `orchestrator`：编排器，串联 research → writing 两个 agent
- `web`：会议室演示（FastAPI + React + SSE），可视化 agent 协作过程

所有 agent 都通过 **JSON-RPC 2.0** 暴露 A2A 协议接口（对齐 [A2A v1.0 规范](https://a2a-protocol.org/latest/specification/)）：
- `GET /.well-known/agent-card.json`：Agent Card（发现，旧路径 `agent.json` 保留为兼容别名）
- `POST /rpc`：JSON-RPC 入口，支持 `SendMessage`、`GetTask`、`CancelTask`、`ListTasks`（旧名 `tasks/send` 等保留为兼容别名）
- `POST /rpc/stream`：SSE 流式入口，支持 `SendStreamingMessage`、`SubscribeToTask`

> 2026-09 更新：数据模型、方法名、枚举值、错误格式与时间戳精度已对齐现行 v1.0.0 规范（PascalCase 方法名、`TASK_STATE_*` / `ROLE_*` 枚举、`google.rpc.ErrorInfo` 错误、毫秒时间戳）。任务失败自动落 `TASK_STATE_FAILED`；支持多轮会话：消息带 `taskId` 续聊既有任务，带 `contextId` 新建任务并继承上下文历史。

---

## 目录结构

```
~/a2a/
├── shared/                 # A2A 共享数据模型 + LLM 客户端
│   ├── __init__.py
│   ├── models.py
│   └── llm_client.py
├── research_agent/         # 研究 agent
│   ├── main.py
│   └── Dockerfile
├── writing_agent/          # 写作 agent
│   ├── main.py
│   └── Dockerfile
├── orchestrator/           # 编排器
│   ├── main.py
│   └── Dockerfile
├── web/                    # 会议室 Web 演示
│   ├── main.py
│   ├── static/
│   │   └── index.html
│   └── Dockerfile
├── docker-compose.yml
├── pyproject.toml          # uv 依赖管理
├── uv.lock                 # uv 锁定文件
├── .env.example
└── README.md
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
# 直接调用 research agent
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

# 流式发送任务（SSE）
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

## 扩展方向

1. **接入真实 LLM**：配置 `LLM_API_KEY` 等环境变量即可启用
2. **增加 agent**：比如加一个 `review-agent` 审校文章（复制现有 agent 改 `process_task` 即可）
3. **动态发现**：orchestrator 启动时抓取各 agent 的 Agent Card 自动注册，按 skill 路由
4. **真流式**：把 LLM 的 token 级输出通过 `SendStreamingMessage` 增量推送（`append` / `lastChunk`）
5. **状态持久化**：把内存任务存储换成 Redis/PostgreSQL
6. **错误重试**：在 orchestrator 里加重试和超时控制
7. **鉴权与安全**：Agent Card 声明 securitySchemes、校验 `A2A-Version`、push notification
8. **K8s 部署**：把每个 service 改成 Deployment + Service

---

## 参考

- [A2A Protocol - Google](https://google.github.io/A2A/)
