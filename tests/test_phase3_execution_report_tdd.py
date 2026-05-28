import tempfile
from pathlib import Path

from flask import Flask
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"


def _build_test_app(tmp_dir: Path):
    from models import db

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{tmp_dir / 'phase3_exec_report.db'}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.drop_all()
        db.create_all()

    return app, db


def _local_tmp_dir() -> Path:
    workspace_tmp = Path("workspace") / "pytest_phase3_exec_report"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=workspace_tmp))


def _seed_execution_report_data(db):
    from models import Requirement, TestCase, TestScript, ExecutionRecord

    requirement = Requirement(
        title="Member center login",
        description="Members log in and open the center home page.",
        raw_text="Members log in and open the center home page.",
        status="executed",
    )
    db.session.add(requirement)
    db.session.flush()

    api_case = TestCase(
        requirement_id=requirement.id,
        title="API login returns token",
        description="Verify login api returns a token.",
        test_type="api",
        priority="high",
        steps=[{"step": 1, "action": "Call login api", "expected": "Token returned"}],
        expected_results=["Token returned"],
    )
    ui_case = TestCase(
        requirement_id=requirement.id,
        title="UI login opens center home",
        description="Verify browser login opens the member center home page.",
        test_type="ui",
        priority="high",
        steps=[{"step": 1, "action": "Login from browser", "expected": "Home page opens"}],
        expected_results=["Home page opens"],
    )
    db.session.add(api_case)
    db.session.add(ui_case)
    db.session.flush()

    api_script = TestScript(
        test_case_id=api_case.id,
        script_type="python",
        script_content="def test_api_login():\n    assert True\n",
        file_path="workspace/scripts/test_api_login.py",
        status="executed",
    )
    ui_script = TestScript(
        test_case_id=ui_case.id,
        script_type="playwright",
        script_content="def test_ui_login():\n    assert False\n",
        file_path="workspace/scripts/test_ui_login.py",
        status="error",
    )
    db.session.add(api_script)
    db.session.add(ui_script)
    db.session.flush()

    db.session.add(
        ExecutionRecord(
            test_script_id=api_script.id,
            status="success",
            result_data={"passed": True, "assertions": 1, "errors": 0},
            execution_time=0.88,
        )
    )
    db.session.add(
        ExecutionRecord(
            test_script_id=ui_script.id,
            status="error",
            result_data={"passed": False, "assertions": 0, "errors": 1},
            error_message="Timeout waiting for home page selector",
            execution_time=12.5,
        )
    )
    db.session.commit()
    return requirement


def test_report_service_includes_execution_summary_sections():
    from service.report_service import report_service

    app, db = _build_test_app(_local_tmp_dir())
    with app.app_context():
        requirement = _seed_execution_report_data(db)
        report = report_service.generate_requirement_report(requirement.id, None)

        assert "Execution Summary" in report.html_content
        assert "API Execution Details" in report.html_content
        assert "UI Execution Details" in report.html_content
        assert "Timeout waiting for home page selector" in report.html_content
        assert "API login returns token" in report.html_content
        assert "UI login opens center home" in report.html_content


def test_report_api_detail_contains_execution_stats():
    from api import api_blueprint
    from service.report_service import report_service

    app, db = _build_test_app(_local_tmp_dir())
    app.register_blueprint(api_blueprint, url_prefix="/api")

    with app.app_context():
        requirement = _seed_execution_report_data(db)
        report = report_service.generate_requirement_report(requirement.id, None)
        report_id = report.id

    client = app.test_client()
    response = client.get(f"/api/reports/{report_id}")

    assert response.status_code == 200
    payload = response.get_json()["report"]
    assert payload["execution_summary"]["total"] == 2
    assert payload["execution_summary"]["success"] == 1
    assert payload["execution_summary"]["error"] == 1
