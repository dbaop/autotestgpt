import sys
import tempfile
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _build_test_app(tmp_dir: Path):
    from api import api_blueprint
    from models import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'screenshot_phase7.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    app.register_blueprint(api_blueprint, url_prefix="/api")

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_screenshot_phase7"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


# ---------------------------------------------------------------------------
# Screenshot service tests
# ---------------------------------------------------------------------------

def test_save_screenshot_from_data_url_writes_png_and_returns_relative_path():
    """save_screenshot_from_data_url should decode a valid base64 data URL and
    return a relative path, and the file should exist on disk."""
    from service.screenshot_service import save_screenshot_from_data_url, ensure_screenshot_dir
    # A minimal 1x1 red PNG, base64-encoded
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    )
    data_url = f"data:image/png;base64,{png_b64}"
    result = save_screenshot_from_data_url(data_url, prefix="tdd_test")
    assert result is not None
    assert result.startswith("screenshots/tdd_test_")
    assert result.endswith(".png")

    abs_dir = ensure_screenshot_dir()
    import os
    full_path = os.path.join(abs_dir, Path(result).name)
    assert os.path.exists(full_path)
    assert os.path.getsize(full_path) > 0
    os.remove(full_path)


def test_save_screenshot_from_data_url_rejects_malformed():
    """Malformed data URLs should return None without raising."""
    from service.screenshot_service import save_screenshot_from_data_url
    assert save_screenshot_from_data_url("not_a_data_url") is None
    assert save_screenshot_from_data_url("") is None


def test_build_screenshot_url_returns_slash_prefixed_path():
    """build_screenshot_url should return a frontend-accessible URL."""
    from service.screenshot_service import build_screenshot_url
    assert build_screenshot_url("screenshots/test.png") == "/screenshots/test.png"


# ---------------------------------------------------------------------------
# ExecutionRecord.screenshot_paths model tests
# ---------------------------------------------------------------------------

def test_execution_record_to_dict_includes_screenshot_paths():
    """ExecutionRecord.to_dict() should include screenshot_paths (empty when None)."""
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import Requirement, TestCase, TestScript, ExecutionRecord

        req = Requirement(title="t", description="d", raw_text="d", status="pending")
        db.session.add(req)
        db.session.flush()
        case = TestCase(requirement_id=req.id, title="tc", test_type="ui")
        db.session.add(case)
        db.session.flush()
        script = TestScript(test_case_id=case.id, script_content="print(1)", script_type="python")
        db.session.add(script)
        db.session.flush()
        rec = ExecutionRecord(
            test_script_id=script.id,
            status="success",
            screenshot_paths=["screenshots/exec_1_before.png", "screenshots/exec_1_after.png"],
        )
        db.session.add(rec)
        db.session.commit()

        d = rec.to_dict()
        assert "screenshot_paths" in d
        assert len(d["screenshot_paths"]) == 2
        assert "screenshots/exec_1_before.png" in d["screenshot_paths"]


def test_execution_record_screenshot_paths_defaults_to_empty():
    """ExecutionRecord without screenshots should return empty list in to_dict()."""
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import Requirement, TestCase, TestScript, ExecutionRecord

        req = Requirement(title="t2", description="d2", raw_text="d2", status="pending")
        db.session.add(req)
        db.session.flush()
        case = TestCase(requirement_id=req.id, title="tc2", test_type="api")
        db.session.add(case)
        db.session.flush()
        script = TestScript(test_case_id=case.id, script_content="print(1)", script_type="python")
        db.session.add(script)
        db.session.flush()
        rec = ExecutionRecord(test_script_id=script.id, status="error")
        db.session.add(rec)
        db.session.commit()

        d = rec.to_dict()
        assert d["screenshot_paths"] == []


# ---------------------------------------------------------------------------
# Document extraction and persistence tests
# ---------------------------------------------------------------------------

def test_start_flow_stores_original_document_in_structured_data():
    """start_flow should persist the extracted doc information."""
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import Requirement
        from service.flow_service import start_flow

        # When providing demand directly (no doc_url), no original_document
        result1 = start_flow({
            "demand": "用户可以通过手机号+验证码登录",
            "title": "Login Test",
            "project_id": 1,
        })
        req1 = db.session.get(Requirement, result1["requirement_id"])
        assert req1 is not None
        sd = req1.structured_data or {}
        # No doc_url means no original_document
        assert "original_document" not in sd


def test_doc_url_with_no_demand_stores_needs_retry_when_cdp_fails():
    """When doc_url is provided and CDP fails, original_document should have needs_retry=True."""
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import Requirement
        from service.flow_service import start_flow

        # Use a doc_url that CDP can't reach
        result = start_flow({
            "doc_url": "https://localhost:19999/never-exists-doc",
            "project_id": 1,
        })
        req = db.session.get(Requirement, result["requirement_id"])
        assert req is not None
        sd = req.structured_data or {}
        doc = sd.get("original_document")
        assert doc is not None
        assert doc.get("url") == "https://localhost:19999/never-exists-doc"
        assert doc.get("needs_retry") is True


def test_original_document_preserved_after_parse_requirement():
    """After ReqAgent.parse_requirement() updates structured_data,
    original_document should be carried forward."""
    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        from models import Requirement
        from flow.test_flow import FlowDataAccess

        req = Requirement(
            title="Preserve Test",
            description="test",
            raw_text="用户登录需求",
            structured_data={
                "test_environment": {},
                "original_document": {
                    "url": "https://example.com/doc",
                    "extracted_content": "## 登录模块\n支持手机号验证码登录",
                    "extracted_at": "2026-01-01T00:00:00",
                },
            },
            status="pending",
        )
        db.session.add(req)
        db.session.commit()

        # Simulate parse_requirement: get orig_doc, process, carry forward
        requirement = FlowDataAccess.get_requirement(req.id)
        orig_doc = (requirement.structured_data or {}).get("original_document")
        assert orig_doc is not None
        assert orig_doc["extracted_content"].startswith("## 登录模块")
