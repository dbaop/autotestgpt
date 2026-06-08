# AutoTestGPT 框架设计方案

## 1. 项目概述

**AutoTestGPT** 是一个多智能体一体化测试平台，实现从需求到测试执行的对话驱动自动化：
- **输入**：自然语言测试需求 / 在线文档链接
- **输出**：结构化需求、测试用例、自动化脚本（Playwright + 可执行 DSL）、执行报告
- **目标**：提高测试效率，降低成本，保证质量

## 2. 架构设计

### 2.1 分层架构

| 层级 | 组件 | 职责 | 技术栈 |
|------|------|------|--------|
| **交互层** | React Web | 需求录入、对话、SSE 实时进度、报告查看 | React + TS + Vite |
| **API 层** | Flask REST + SSE | 路由、事件流 | Flask + Blueprint |
| **编排层** | ConversationOrchestrator | 对话驱动状态机、自动驱动、人在环确认 | `agent/orchestrator.py` |
| **智能体层** | 六大 Agent | 解析/探索/用例/代码/执行/审查 | LiteLLM + 多模型 |
| **执行层** | CDP UI Runner / ExecAgent | UI 走真实浏览器（CDP），API 走 pytest | BrowserProbe / pytest |
| **服务层** | Service 模块 | 知识库、审查、缺陷、报告、截图、浏览器探针、SSE | Python |
| **存储层** | SQLAlchemy + MySQL/SQLite | 持久化 | ORM |

> 说明：早期设计中的 OpenClaw（前端）与 LiteFlow（同步流水线）已被 **React 前端** 与 **ConversationOrchestrator** 取代；`flow/test_flow.py` 的 `AutoTestFlow` 作为遗留同步流水线保留（默认不启用），其 `FlowDataAccess` 仍被编排器复用做落库。

### 2.2 智能体

| 智能体 | 输入 | 处理 | 产出（artifact / 落库） |
|--------|------|------|------------------------|
| **ReqAgent** | 自然语言需求 / 文档内容 | LLM 解析 | `structured_requirement` |
| **BrowserAgent** | 测试地址 | CDP 打开页面、抓真实 DOM | `page_map`（真实选择器） |
| **CaseAgent** | 结构化需求 + page_map | LLM 设计 + 知识库复用 | `test_cases` → `TestCase` 表 |
| **CodeAgent** | 用例 + page_map | LLM 生成 | `test_scripts` → `TestScript` 表（UI 同时含 Playwright `code` + GWT `dsl`） |
| **ExecAgent** | API 脚本 | pytest 子进程 | `ExecutionRecord` |
| **ReviewAgent** | Git 变更（可选） | LLM 审查 | 缺陷候选 / 审查结论 |

智能体基于 `ToolCapableAgent.act()`（`agent/tool_agent.py`）的事件协议工作，yield `message / tool_call / tool_result / question / artifact / error / done`；`question`（ask_user）触发暂停，由编排器保存 checkpoint 并等待用户回复。

## 3. 编排设计（ConversationOrchestrator）

### 3.1 驱动循环 `_drive`

按 `requirement.status` 反复推进，直到暂停或终态：

```
pending ─ReqAgent─▶ parsed
  └─[确认 gate]─ 等用户确认（测试地址/账号/是否 review）
parsed(已确认) ─BrowserAgent─▶ probed ─CaseAgent─▶ cases_generated
  ─CodeAgent─▶ code_generated ─[确定性执行]─▶ executed ─[finalize]─▶ completed
```

- **状态机**：`STATUS_TO_PHASE` 决定每个状态由哪个 agent / 特判处理；`ARTIFACT_STATUS_MAP` 决定 artifact 落库后状态如何前进。
- **防失控**：`MAX_DRIVE_STEPS` 上限；某步状态未前进则停下并提示（避免死循环）。
- **暂停-恢复**：agent 提问或 gate 触发 → 写 `waiting_user` 事件 + checkpoint；用户回复后清除等待态并按当前状态重新驱动（不依赖 generator.send 续跑大模型）。

### 3.2 结构化确认 gate（人在环）

需求解析完成（`parsed`）后，编排器发一条结构化消息列出【测试地址 / 账号·登录方式·凭据 / 是否需要代码 review（带预设默认值）】，暂停等待用户在对话里一次确认或补全。回复经 `_parse_confirmation_reply` 解析（环境正则 + review 意向）落库后继续。

### 3.3 确定性执行

执行阶段不靠大模型，而是编排器直接取该需求的 `TestScript` 逐个执行并写 `ExecutionRecord`：

- `script_type == "ui_cdp"` → `service/ui_runner_service.run_ui_dsl`（CDP 真实浏览器）
- `script_type == "playwright"` 且存在同用例的 `ui_cdp` 兄弟 → 跳过（纯交付物）
- 其余（`python` 等）→ `ExecAgent.process`（pytest 子进程）

### 3.4 收尾 finalize

`executed` 后：可选 `run_review_task`（Git 审查）→ `defect_service.analyze_requirement` → `report_service.generate_requirement_report`（合并 HTML）→ `completed`，并通过 SSE 推送报告链接。

## 4. UI 执行：CDP 通道

### 4.1 BrowserProbe 三级后端（`service/browser_probe_service.py`）

1. **CDP Bridge MCP**（`:18700`）——操控用户带登录态的真实 Chrome（与 `/browser-automation` skill 同源）
2. **直连 CDP**（`:9222`）
3. **standalone Chromium**（Playwright 启动，兜底）

统一暴露同步方法：`navigate / snapshot / screenshot / click / fill / execute_js / get_network_requests / extract_content`。

### 4.2 GWT DSL 与 UI Runner（`service/ui_runner_service.py`）

UI 用例以 Given-When-Then JSON 表示并逐步执行：`given.navigate` → `when`（fill/click/select/wait）→ `then`（url_contains / element_visible / element_text / element_count）。断言统一经 `execute_js` 求值（跨三后端一致）；逐步操作避免一次性 JS blob 在导航后丢上下文；采集前后截图。返回结构与 `ExecAgent.process` 同构，便于统一落 `ExecutionRecord`。

## 5. 数据模型

核心表与关系：

```
Requirement 1──* TestCase 1──* TestScript 1──* ExecutionRecord
Requirement 1──* Conversation 1──* Message          （对话 / SSE）
Requirement 1──* AgentEvent                          （进度 / waiting_user）
Requirement 1──* DefectCandidate / FinalReport       （缺陷 / 报告）
CodeReviewTask 1──* CodeReviewFinding                 （代码审查）
```

`Requirement.structured_data` (JSON) 承载：`structured_requirement`、`page_map`、`test_environment`、`review` 预设、`confirmation` 确认态等（就地修改需 `flag_modified`）。

## 6. 数据流

```
React 前端 ──POST /flow/start──▶ flow_service.start_flow
                                   │ 建 Requirement + Conversation，后台线程执行
                                   ▼
                         ConversationOrchestrator._drive ──SSE──▶ 前端实时进度/提问
                                   │  artifact 落库（FlowDataAccess）
                                   ▼
              CDP UI Runner / ExecAgent ─▶ ExecutionRecord ─▶ report_service ─▶ FinalReport
```

## 7. 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| 语言 | Python 3.10+ / TypeScript | 后端 / 前端 |
| Web | Flask | API + SSE |
| ORM | SQLAlchemy + MySQL/SQLite | 持久化 |
| LLM | LiteLLM（MiniMax / DeepSeek / OpenAI / 豆包） | 多模型统一调用 |
| 浏览器 | CDP Bridge MCP / CDP / Playwright | UI 真实执行 |
| 测试执行 | pytest | API 脚本 |
| 前端 | React + Vite | 交互界面 |

## 8. 部署

```bash
pip install -r requirements.txt
playwright install chrome          # standalone 兜底
python main.py                     # http://localhost:8000
# 前端：cd autotestgptFront && npm install && npm run dev
```

- `CONVERSATION_FLOW_ENABLED=true`（默认）启用对话驱动编排。
- 可选启动 CDP Bridge（`:18700`）以操控真实 Chrome；否则自动 standalone。
- 生产建议 MySQL 8.0+；Gunicorn + Nginx 反代。

## 9. 扩展计划

- **接口回归**：将接口测试全流程 case 接入，实现「接口回归 + UI 自动化」并行。
- **自愈执行**：UI 执行失败时用 CDP snapshot 比对、自动修正选择器（ExecAgent 已具备 script_fix 基础）。
- **更强探索**：BrowserAgent 多页面/多流程遍历，提升 page_map 覆盖。
- **报告增强**：UI 逐步结果/截图在报告中结构化呈现；PDF 导出。
- **集成**：Jira / GitLab CI / 监控告警。

## 10. 现状说明

- 主链路（解析 → 确认 → 探索 → 用例 → 代码 → 执行 → 报告）已在 orchestrator 模式打通。
- UI 执行已对接 CDP 通道（GWT DSL）；API 执行维持 pytest。
- 遗留 `AutoTestFlow` 同步流水线保留但默认不启用。
