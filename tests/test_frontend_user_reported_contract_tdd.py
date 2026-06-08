from pathlib import Path


FRONTEND_SRC = Path("autotestgptFront") / "src"


def _read_source(relative_path: str) -> str:
    return (FRONTEND_SRC / relative_path).read_text(encoding="utf-8")


def test_frontend_exposes_knowledge_base_file_binding_page():
    app_source = _read_source("App.tsx")
    layout_source = _read_source("components/Layout.tsx")
    knowledge_page = FRONTEND_SRC / "pages" / "KnowledgeBases.tsx"

    assert 'path="knowledge-bases"' in app_source
    assert "知识库" in layout_source
    assert knowledge_page.exists()

    page_source = knowledge_page.read_text(encoding="utf-8")
    assert "knowledgeBasesApi.importFile" in page_source
    assert "绑定文件到知识库" in page_source
    assert 'type="file"' in page_source


def test_new_test_page_can_include_review_in_full_workflow():
    source = _read_source("pages/NewTest.tsx")

    assert "reviewEnabled" in source
    assert "reviewRepoUrl" in source
    assert "reviewBranch" in source
    assert "reviewDays" in source
    assert "review:" in source
    assert "代码 Review 纳入完整流程" in source


def test_frontend_css_loads_remote_fonts_before_tailwind_directives():
    source = _read_source("index.css")
    meaningful_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip() and not line.strip().startswith("/*")
    ]

    assert meaningful_lines[0].startswith("@import url(")
    assert meaningful_lines[1:4] == ["@tailwind base;", "@tailwind components;", "@tailwind utilities;"]


def test_layout_exposes_accessible_shell_controls():
    source = _read_source("components/Layout.tsx")

    assert 'aria-label="切换主题"' in source
    assert 'aria-label={mobileOpen ? \'关闭导航\' : \'打开导航\'}' in source
    assert 'aria-current={active ? \'page\' : undefined}' in source


def test_frontend_exposes_agent_workbench_page():
    app_source = _read_source("App.tsx")
    layout_source = _read_source("components/Layout.tsx")
    api_source = _read_source("api.ts")
    workbench_page = FRONTEND_SRC / "pages" / "AgentWorkbench.tsx"

    assert 'path="workbench"' in app_source
    assert "Agent 工作台" in layout_source
    assert "agentWorkbenchApi" in api_source
    assert workbench_page.exists()

    page_source = workbench_page.read_text(encoding="utf-8")
    assert "BrowserAgent" in page_source
    assert "agent-browser" in page_source
    assert "Playwright" in page_source
    assert "人工介入" in page_source


def test_frontend_chat_phase5_summary_panel():
    chat_source = _read_source("pages/Chat.tsx")
    api_source = _read_source("api.ts")
    detail_source = _read_source("pages/RequirementDetail.tsx")

    assert "getAgentContext" in api_source
    assert "pending_questions" in chat_source
    assert "Agent 工作台" in chat_source
    assert "/workbench/" in detail_source
    assert "对话协作" in detail_source


def test_frontend_chat_bootstrap_copy_and_workbench_resume_contract():
    chat_source = _read_source("pages/Chat.tsx")
    workbench_source = _read_source("pages/AgentWorkbench.tsx")

    assert "输入需求后，Agent 会自动补齐信息并启动测试" in chat_source
    assert "flowApi.resume" in workbench_source
    assert "保存并继续测试" in workbench_source
    assert "loginState === 'pre_authenticated' && !credentialRef.trim()" in workbench_source
    assert "missing.push({ key: 'repo'" not in workbench_source
    assert "missing.push({ key: 'branch'" not in workbench_source


def test_execution_records_render_full_error_details():
    source = _read_source("pages/Executions.tsx")

    assert "<details" in source
    assert "完整错误" in source
    assert "whiteSpace: 'pre-wrap'" in source
    assert "textOverflow: 'ellipsis'" not in source


def test_agent_workbench_has_polished_operational_layout():
    source = _read_source("pages/AgentWorkbench.tsx")

    assert "workbench-hero" in source
    assert "agent-rail" in source
    assert "timeline-panel" in source
    assert "补齐环境后继续执行" in source


def test_orchestrator_mode_enabled_by_default():
    from config import Config
    # Default should be orchestrator mode (CONVERSATION_FLOW_ENABLED != "false")
    assert Config.CONVERSATION_FLOW_ENABLED is True


def test_orchestrator_detects_env_from_chat_message():
    """_try_save_env_from_message should detect test_url and login_state from chat."""
    import sys
    import tempfile
    from pathlib import Path as _Path

    from flask import Flask
    import werkzeug
    if not hasattr(werkzeug, "__version__"):
        werkzeug.__version__ = "3"

    RO = _Path(__file__).resolve().parents[1]
    if str(RO) not in sys.path:
        sys.path.insert(0, str(RO))

    from agent.orchestrator import ConversationOrchestrator
    from models import db, Requirement

    app = Flask(__name__)
    orch_tmp = _Path("workspace") / "pytest_orch_env"
    orch_tmp.mkdir(parents=True, exist_ok=True)
    tmp = _Path(tempfile.mkdtemp(dir=orch_tmp))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp / 'orch_env.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        req = Requirement(
            title="Test", description="test", raw_text="test",
            structured_data={}, execution_progress={}, status="pending",
        )
        db.session.add(req)
        db.session.commit()

        orch = ConversationOrchestrator()

        # Test URL detection
        result = orch._try_save_env_from_message(req, "测试地址 https://staging.example.com", 1)
        assert result is not None
        assert "测试地址" in result
        env = (req.structured_data or {}).get("test_environment", {})
        assert env.get("test_url") == "https://staging.example.com"

        # Login state detection
        result2 = orch._try_save_env_from_message(req, "登录态 no_login_required", 1)
        assert result2 is not None
        assert "登录态" in result2
        env2 = (req.structured_data or {}).get("test_environment", {})
        assert env2.get("login_state") == "no_login_required"

        # Credential detection
        result3 = orch._try_save_env_from_message(req, "凭据 vault://login/admin", 1)
        assert result3 is not None
        assert "凭据" in result3
        env3 = (req.structured_data or {}).get("test_environment", {})
        assert env3.get("credential_ref") == "vault://login/admin"

        # Non-env message should return None
        result4 = orch._try_save_env_from_message(req, "你好，请开始分析需求", 1)
        assert result4 is None

        db.session.remove()
