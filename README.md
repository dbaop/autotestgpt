# AutoTestGPT

多智能体一体化测试平台：从需求文档出发，经「**解析 → 结构化确认 → 探索页面 → 设计用例 → 生成脚本 → 执行 → 出报告**」的对话驱动流程，实现 UI 自动化测试的全链路自动化。

- **输入**：自然语言需求 / 在线文档链接（钉钉、飞书、语雀等）
- **输出**：结构化需求、测试用例、自动化脚本（Playwright + 可执行 DSL）、执行报告
- **执行**：UI 用例走 CDP 通道（真实浏览器），API 用例走 pytest（接口回归后续接入）

> 本项目仍在迭代中，接口可能调整。

## 架构设计

### 分层架构

| 层级 | 组件 | 职责 | 技术栈 |
|------|------|------|--------|
| **交互层** | React Web 界面 | 需求录入、对话、实时进度（SSE）、报告查看 | React + TypeScript + Vite |
| **API 层** | Flask REST API | 路由、SSE 事件流 | Flask + Blueprint |
| **编排层** | ConversationOrchestrator | 对话驱动的状态机、自动驱动到底、人在环确认 | Python（`agent/orchestrator.py`）|
| **智能体层** | 六大 Agent | 需求解析、页面探索、用例设计、代码生成、执行、代码审查 | LiteLLM + 多模型 |
| **执行层** | CDP UI Runner / ExecAgent / 执行器 | UI 经 CDP 真实浏览器执行；API 经 pytest 子进程 | BrowserProbe(CDP) / pytest |
| **服务层** | Service 模块 | 知识库、代码审查、缺陷分析、报告、截图、浏览器探针 | Python |
| **持久层** | SQLAlchemy + MySQL/SQLite | 数据持久化 | SQLAlchemy ORM |

### 智能体矩阵

| 智能体 | 职责 | 产出 artifact | 落库后状态 |
|--------|------|---------------|------------|
| **ReqAgent** | 需求解析 | `structured_requirement` | `parsed` |
| **BrowserAgent** | 页面探索（CDP 抓真实 DOM 选择器） | `page_map` | `probed` |
| **CaseAgent** | 用例设计（含知识库复用） | `test_cases` → `TestCase` 表 | `cases_generated` |
| **CodeAgent** | 代码生成（UI 同时产出 Playwright + GWT DSL） | `test_scripts` → `TestScript` 表 | `code_generated` |
| **ExecAgent** | 执行 API 脚本（pytest 子进程） | `ExecutionRecord` | `executed` |
| **ReviewAgent** | 代码审查（可选，需求确认时开启） | `review_findings` / 缺陷 | — |

> UI 用例的执行不依赖 ExecAgent/pytest，而是由 **CDP UI Runner**（`service/ui_runner_service.py`）逐步执行 GWT DSL（见下文）。

### 编排：ConversationOrchestrator

对话驱动的状态机（`agent/orchestrator.py`），核心是 `_drive` 驱动循环：按 `requirement.status` 一路推进到底，遇到智能体提问或确认 gate 就**暂停**，用户回复后**继续驱动**。

```
pending ──ReqAgent──▶ parsed
   │
   ├─（确认 gate：测试地址 / 账号·登录 / 是否代码 review）── 等用户确认
   ▼
parsed(已确认) ──BrowserAgent──▶ probed ──CaseAgent──▶ cases_generated
   ──CodeAgent──▶ code_generated ──[确定性执行]──▶ executed ──[finalize]──▶ completed
```

- **结构化确认 gate**：需求解析完成后，智能体用一条消息列出【测试地址 / 账号·登录方式·凭据 / 是否需要代码 review（带预设默认值）】让用户一次确认或补全（人在环，复用提问-暂停-恢复机制）。
- **确定性执行**：编排器直接取该需求的 `TestScript` 列表逐个执行（UI→CDP，API→pytest），写入 `ExecutionRecord`，不依赖大模型「执行」。
- **收尾 finalize**：可选代码审查 → 缺陷分析 → 生成合并 HTML 报告 → `completed`，并通过 SSE 推送报告链接。

### UI 执行：对接 /browser-automation（CDP 通道）

UI 用例在**真实浏览器**里执行，复用 `BrowserProbe`（`service/browser_probe_service.py`），后端三级自动兜底：

1. **CDP Bridge MCP**（`http://localhost:18700`）—— 操控用户带登录态的真实 Chrome（推荐，与 `/browser-automation` skill 同源）
2. **直连 CDP**（`http://localhost:9222`，`--remote-debugging-port`）
3. **standalone Chromium**（Playwright 启动，最后兜底）

CodeAgent 为每个 UI 用例同时产出：
- `code`：Playwright Python 脚本（**交付物**，存档/人工复用，不自动执行）
- `dsl`：Given-When-Then JSON（**可执行**，由 CDP UI Runner 逐步跑）

GWT DSL 规格（对齐 browser-automation skill 的 functional-testing 模块）：

```json
{
  "given": { "action": "navigate", "url": "/login" },
  "when": [
    { "action": "fill",  "selector": "#username", "value": "admin" },
    { "action": "click", "selector": "button[type=submit]" }
  ],
  "then": [
    { "type": "url_contains",    "value": "/dashboard" },
    { "type": "element_visible", "selector": ".welcome" },
    { "type": "element_text",    "selector": ".user", "contains": "admin" },
    { "type": "element_count",   "selector": ".row", "min": 1 }
  ]
}
```

- `when.action` ∈ `navigate | fill | click | select | wait`
- `then.type` ∈ `url_contains | element_visible | element_text | element_count`
- 选择器取自 BrowserAgent 探索出的 `page_map`（真实 DOM）；执行时逐步操作并采集前后截图，每个 UI 用例落一条 `ExecutionRecord`（含 steps/assertions/截图）。

### 支持的 LLM

按可用 API Key 自动选择（`agent/base_agent.py`）：MiniMax / DeepSeek / OpenAI / 豆包 Doubao。

## 目录结构

```
autotestgpt/
├── agent/                      # 智能体
│   ├── base_agent.py           # 基础类（LLM 调用、JSON 解析）
│   ├── tool_agent.py           # 工具能力基类（act() 事件协议、工具调用）
│   ├── tools.py                # 工具集（ask_user / search_knowledge_base / browser_* …）
│   ├── orchestrator.py         # ★ ConversationOrchestrator：对话驱动状态机
│   ├── req_agent.py            # 需求解析
│   ├── browser_agent.py        # 页面探索（CDP）
│   ├── case_agent.py           # 用例设计
│   ├── code_agent.py           # 代码生成（Playwright + GWT DSL）
│   ├── exec_agent.py           # API 执行（pytest 子进程）
│   └── review_agent.py         # 代码审查
├── api/routes/                 # 路由：flow / conversations / requirements / test_cases /
│                               #       executions / reports / code_reviews / knowledge_bases …
├── service/                    # 业务服务
│   ├── flow_service.py         # start_flow / resume_flow（编排入口）
│   ├── ui_runner_service.py    # ★ CDP UI 执行引擎（run_ui_dsl）
│   ├── browser_probe_service.py# BrowserProbe（CDP 三级后端）
│   ├── cdp_bridge_client.py    # cdp-bridge MCP 客户端
│   ├── screenshot_service.py   # 截图持久化
│   ├── report_service.py       # 合并 HTML 报告
│   ├── defect_service.py       # 缺陷分析
│   ├── review_service.py       # Git 代码审查
│   ├── knowledge_service.py    # 知识库
│   ├── sse_service.py          # SSE 事件推送
│   └── …                       # checkpoint / agent_event / chat_summary …
├── flow/test_flow.py           # 遗留同步流水线 AutoTestFlow + FlowDataAccess（落库工具，仍被复用）
├── executor/                   # api_executor.py / ui_executor.py（遗留）
├── autotestgptFront/           # React 前端
├── templates/report.html       # 单脚本报告模板
├── tests/                      # 测试套件
├── models.py                   # 数据库模型
├── config.py                   # 配置
└── main.py                     # 应用入口
```

## 快速开始

### 1. 环境准备

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
playwright install chrome           # standalone 兜底执行需要
```

### 2. 配置环境变量（`.env`）

```env
# LLM API Keys（按可用项自动选择，至少配一个）
MINIMAX_API_KEY=
DEEPSEEK_API_KEY=
OPENAI_API_KEY=
DOUBAO_API_KEY=

# 编排开关：对话驱动流程（默认开启；设为 false 走遗留同步流水线）
CONVERSATION_FLOW_ENABLED=true

# 数据库（不配则回退到 instance/ 下的 SQLite；生产建议 MySQL 8.0+）
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=autotestgpt

# 服务器
SERVER_PORT=8000
```

> CDP Bridge（`http://localhost:18700`）为可选：启动后 UI 执行会操控你带登录态的真实 Chrome；未启动则自动兜底 standalone Chromium。

### 3. 启动

```bash
python main.py            # http://localhost:8000，数据库表自动创建
# 前端：cd autotestgptFront && npm install && npm run dev
```

## 使用方式

推荐通过前端：录入需求（或文档链接）→ 在对话里回复确认 gate（地址/账号/是否 review）→ 系统自动跑到出报告。

也可直接调 API：

```bash
# 启动流程（orchestrator 模式返回 conversation_id）
curl -X POST http://localhost:8000/api/flow/start \
  -H "Content-Type: application/json" \
  -d '{"title":"登录测试","demand":"测试登录功能……",
       "test_environment":{"test_url":"https://example.com"},
       "review":{"repo_url":"https://github.com/org/repo","branch":"main","days":7}}'

# 在对话里发送消息（推进流程 / 回复确认 gate）
curl -X POST http://localhost:8000/api/conversations/<id>/messages \
  -H "Content-Type: application/json" -d '{"content":"确认"}'

# 查看报告（HTML）
curl http://localhost:8000/api/reports/<report_id>/preview
```

## 主要 API

| 功能 | 方法 | 路径 |
|------|------|------|
| 启动流程 | POST | `/api/flow/start` |
| 流程状态 | GET | `/api/flow/status/<id>` |
| 恢复流程 | POST | `/api/flow/resume/<id>` |
| 发送消息 | POST | `/api/conversations/<id>/messages` |
| SSE 事件流 | GET | `/api/conversations/<id>/stream` |
| 需求 CRUD / 导入 | * | `/api/requirements …` |
| 用例 / 执行记录 | GET | `/api/cases`、`/api/executions` |
| 生成报告 | POST | `/api/reports` |
| 报告查看 | GET | `/api/reports/<id>` · `/api/reports/<id>/preview` |
| 代码审查 / 知识库 | * | `/api/code-reviews`、`/api/knowledge-bases …` |

## 监控与日志

- 应用日志：`workspace/logs/autotestgpt.log`
- 执行脚本：`workspace/scripts/`、`workspace/ui_tests/`
- 截图：`workspace/screenshots/`
- 报告：`report/html/`、`report/json/`（单脚本）；合并报告存 `final_reports` 表，经 `/api/reports/<id>/preview` 查看

## 许可证

MIT。
