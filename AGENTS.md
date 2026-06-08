# AGENTS.md — 仓库约定（供 AI/协作者参考）

本仓库是 **Python 后端 + React 前端** 的双栈项目，请按对应栈的约定改动。

## 技术栈与约定

### 后端（根目录）
- 语言：Python 3.10+；Flask + SQLAlchemy。
- 风格：snake_case；模块/服务分层（`agent/` 智能体、`service/` 业务、`api/routes/` 路由）。
- 测试：pytest，位于 `tests/`（文件名 `test_*_tdd.py`）。运行：`python -m pytest tests/ -q`。
- 数据库：默认 MySQL 8.0+（未配 DB_* 时回退到 `instance/` 下 SQLite）。

### 前端（`autotestgptFront/`）
- 语言：TypeScript；React + Vite。
- 类型检查：`npx tsc --noEmit`。

## 核心架构（改动前必读）

- **编排入口**：`agent/orchestrator.py` 的 `ConversationOrchestrator._drive` —— 对话驱动状态机，按 `requirement.status` 自动推进；遇 `question`/确认 gate 暂停，用户回复后继续。
- **流程启动**：`service/flow_service.py::start_flow`（建 Requirement + Conversation，后台线程跑编排器）。
- **智能体**：基于 `agent/tool_agent.py::ToolCapableAgent.act()` 的事件协议（`message/tool_call/tool_result/question/artifact/error/done`）。
- **artifact 落库**：统一在 `orchestrator._handle_artifact`（复用 `flow/test_flow.py::FlowDataAccess`）；**不要**在各 agent 的 `act()` 里落库（其 `process()` 仍被遗留 `AutoTestFlow` 复用，会双写）。
- **执行**：UI → `service/ui_runner_service.py::run_ui_dsl`（CDP 真实浏览器，GWT DSL）；API → `agent/exec_agent.py::ExecAgent.process`（pytest）。
- **浏览器通道**：`service/browser_probe_service.py::BrowserProbe`（CDP Bridge MCP → 直连 CDP → standalone 三级兜底）。
- **报告**：`service/report_service.py::generate_requirement_report`（合并 HTML，存 `FinalReport`，经 `/api/reports/<id>/preview` 查看）。

## 改动注意

- 对 `Requirement.structured_data` / `execution_progress` 等 JSON 列就地修改后，必须 `flag_modified(obj, "字段名")`，否则不落库。
- `FlowDataAccess.create_execution_record` 只 `add()` 不 `commit()`，调用后需显式 `db.session.commit()`。
- 后台线程内的 DB 操作必须有 Flask app context（参考 `flow_service._run_orchestrator_in_thread`）。
- 不要修改遗留 `flow/test_flow.py::AutoTestFlow` 的行为（默认不启用）；可只读复用 `FlowDataAccess`。

## 提交

- Conventional Commits（如 `feat:`、`fix:`）。仅在被明确要求时提交/推送。
