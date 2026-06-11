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


def test_env_message_echoing_unchanged_url_is_not_a_change():
    """Re-run regression: the synthetic resume message echoes the already-saved
    test_url. That must NOT be detected as a mid-flow env change, otherwise the
    orchestrator cancels the flow instead of re-executing scripts."""
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
    orch_tmp = _Path("workspace") / "pytest_orch_env_unchanged"
    orch_tmp.mkdir(parents=True, exist_ok=True)
    tmp = _Path(tempfile.mkdtemp(dir=orch_tmp))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp / 'orch_env2.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        url = "https://staging.example.com"
        req = Requirement(
            title="Test", description="test", raw_text="test",
            structured_data={"test_environment": {"test_url": url}},
            execution_progress={"test_environment": {"test_url": url}},
            status="code_generated",
        )
        db.session.add(req)
        db.session.commit()

        orch = ConversationOrchestrator()

        # Same as flow_service.resume_flow's synthetic re-run message.
        msg = f"测试地址 {url} 已配置，请开始探索页面并推进测试流程"
        result = orch._try_save_env_from_message(req, msg, 1)
        assert result is None  # unchanged → not reported as an env change

        # A genuinely different URL is still detected.
        result2 = orch._try_save_env_from_message(
            req, "测试地址 https://prod.example.com", 1
        )
        assert result2 is not None
        assert "测试地址" in result2

        db.session.remove()


def _orch_app(tmp_name: str):
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

    from models import db

    app = Flask(__name__)
    base = _Path("workspace") / tmp_name
    base.mkdir(parents=True, exist_ok=True)
    tmp = _Path(tempfile.mkdtemp(dir=base))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp / 'orch.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def test_handle_artifact_preserves_user_supplied_title():
    """User enters a title in the New Test form; the requirement-parsing artifact
    must NOT overwrite it, otherwise the title disappears from the requirement
    list. An auto-generated placeholder title, however, should still be filled."""
    app = _orch_app("pytest_orch_title")

    from agent.orchestrator import ConversationOrchestrator
    from models import db, Requirement

    with app.app_context():
        db.create_all()
        orch = ConversationOrchestrator()

        # 1) User-supplied title is preserved (not overwritten by parsed title).
        user_req = Requirement(
            title="会员中心登录需求", description="d", raw_text="r",
            structured_data={}, status="pending",
        )
        db.session.add(user_req)
        db.session.commit()
        orch._handle_artifact(
            user_req, "structured_requirement",
            {"title": "LLM 解析出来的标题", "description": "parsed"}, 0,
        )
        db.session.refresh(user_req)
        assert user_req.title == "会员中心登录需求"
        assert user_req.description == "parsed"

        # 2) Auto-generated placeholder title is filled from the parsed result.
        ph_req = Requirement(
            title="Requirement-20260611-101010", description="d", raw_text="r",
            structured_data={}, status="pending",
        )
        db.session.add(ph_req)
        db.session.commit()
        orch._handle_artifact(
            ph_req, "structured_requirement",
            {"title": "解析标题", "description": "parsed"}, 0,
        )
        db.session.refresh(ph_req)
        assert ph_req.title == "解析标题"

        db.session.remove()


def test_orchestrator_executes_api_python_scripts_before_report():
    """README promises API scripts run via pytest. A generated API python script
    must be treated as executable instead of being filtered out and reported as
    "nothing to run"."""
    app = _orch_app("pytest_orch_api_exec")

    from agent.orchestrator import ConversationOrchestrator
    from models import Conversation, ExecutionRecord, Requirement, TestCase, TestScript, db

    with app.app_context():
        db.create_all()
        req = Requirement(
            title="API smoke", description="d", raw_text="r",
            structured_data={}, status="code_generated",
        )
        db.session.add(req)
        db.session.flush()
        conv = Conversation(title="c", requirement_id=req.id)
        db.session.add(conv)
        case = TestCase(
            requirement_id=req.id,
            title="TC-API-001 查询列表",
            description="api",
            test_type="api",
            priority="high",
        )
        db.session.add(case)
        db.session.flush()
        script = TestScript(
            test_case_id=case.id,
            script_type="python",
            script_content="def test_api():\n    assert True\n",
            file_path="workspace/scripts/test_api.py",
            status="generated",
        )
        db.session.add(script)
        db.session.commit()

        orch = ConversationOrchestrator()
        calls = []

        def fake_process(payload):
            calls.append(payload)
            return {
                "status": "success",
                "execution_time": 0.01,
                "result": {"passed": True},
                "error": None,
            }

        orch._agents["exec_agent"].process = fake_process

        events = list(orch._run_execution(conv.id, req))

        db.session.refresh(req)
        assert calls and calls[0]["script_id"] == script.id
        assert req.status == "executed"
        assert ExecutionRecord.query.filter_by(test_script_id=script.id).count() == 1
        assert not any(event.get("key") == "final_report" for event in events)

        db.session.remove()


def test_orchestrator_does_not_mark_executed_when_no_executable_scripts_exist():
    """A UI Playwright deliverable without a ui_cdp DSL is not automatically
    executable. The orchestrator must stop in an error state instead of moving
    to executed, because executed immediately triggers report generation."""
    app = _orch_app("pytest_orch_no_executable")

    from agent.orchestrator import ConversationOrchestrator
    from models import Conversation, ExecutionRecord, Requirement, TestCase, TestScript, db

    with app.app_context():
        db.create_all()
        req = Requirement(
            title="UI flow", description="d", raw_text="r",
            structured_data={"test_environment": {"test_url": "https://example.test"}},
            execution_progress={"test_environment": {"test_url": "https://example.test"}},
            status="code_generated",
        )
        db.session.add(req)
        db.session.flush()
        conv = Conversation(title="c", requirement_id=req.id)
        db.session.add(conv)
        case = TestCase(
            requirement_id=req.id,
            title="TC-UI-001 登录",
            description="ui",
            test_type="ui",
            priority="high",
        )
        db.session.add(case)
        db.session.flush()
        db.session.add(
            TestScript(
                test_case_id=case.id,
                script_type="playwright",
                script_content="from playwright.sync_api import Page\n",
                file_path="workspace/scripts/test_ui.py",
                status="generated",
            )
        )
        db.session.commit()

        orch = ConversationOrchestrator()
        events = list(orch._run_execution(conv.id, req))

        db.session.refresh(req)
        assert req.status == "error"
        assert req.execution_progress["completed"] is False
        assert "没有可执行" in req.execution_progress["error"]
        assert ExecutionRecord.query.count() == 0
        assert any(event.get("type") == "error" for event in events)

        db.session.remove()

