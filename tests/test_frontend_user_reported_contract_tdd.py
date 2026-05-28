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

