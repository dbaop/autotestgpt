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
